"""
Call to Arms
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timedelta, time
from typing import Optional, Dict, List, Tuple, Set, Literal, Iterable
import os, base64, math

import streamlit as st
from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy.pool import NullPool

# ===================== Config & State =====================

st.set_page_config(page_title="Call to Arms — Pairings", layout="wide")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", "change-me"))
LOGO_URL = st.secrets.get("LOGO_URL", os.getenv("LOGO_URL", ""))
LOGO_WIDTH = int(st.secrets.get("LOGO_WIDTH", os.getenv("LOGO_WIDTH", 120)))
DATABASE_URL = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))  # optional (Postgres); default local SQLite
DB_PATH = "pairings_db.sqlite"



LOGO_TOW_URL = st.secrets.get("TOW_LOGO_URL", os.getenv("TOW_LOGO_URL", ""))
LOGO_HH_URL = st.secrets.get("HH_LOGO_URL", os.getenv("HH_LOGO_URL", ""))
HEADER_LOGO_WIDTH = int(st.secrets.get("HEADER_LOGO_WIDTH", os.getenv("HEADER_LOGO_WIDTH", 120)))
ELEMENT_URL = st.secrets.get("ELEMENT_GAMES_URL", os.getenv("ELEMENT_GAMES_URL", ""))
ELEMENT_LOGO_URL = st.secrets.get("ELEMENT_LOGO_URL", os.getenv("ELEMENT_LOGO_URL", ""))
DISCORD_URL = st.secrets.get("DISCORD_URL", os.getenv("DISCORD_URL", ""))
DISCORD_LOGO_URL = st.secrets.get("DISCORD_LOGO_URL", os.getenv("DISCORD_LOGO_URL", ""))
SYSTEMS: List[str] = ["TOW", "Horus Heresy"]

# Shared factions list can be tailored per-system later; re-using OW list as a baseline.
PLACEHOLDER_FACTIONS: List[str] = [
    'Empire of Man', 'Dwarfen Mountain Holds', 'Kingdom of Bretonnia',
    'Wood Elf Realms', 'High Elf Realms', 'Orc & Goblin Tribes',
    'Warriors of Chaos', 'Beastmen Brayheards', 'Tomb Kings of Khemri',
    'Skaven', 'Ogre Kingdoms', 'Lizardmen', 'Chaos Dwarfs', 'Dark Elves',
    'Daemons of Chaos', 'Vampire Counts', 'Grand Cathay'
]
PLACEHOLDER_FACTIONS_WITH_BLANK: List[str] = ["— None —", *PLACEHOLDER_FACTIONS]
# Horus Heresy factions (Legions & forces) for signup
HH_FACTIONS: List[str] = [
    "I - Dark Angels",
    "III - Emperor's Children",
    "IV - Iron Warriors",
    "V - White Scars",
    "VI - Space Wolves",
    "VII - Imperial Fists",
    "VIII - Night Lords",
    "IX - Blood Angels",
    "X - Iron Hands",
    "XII - World Eaters",
    "XIII - Ultramarines",
    "XIV - Death Guard",
    "XV - Thousand Sons",
    "XVI - Sons of Horus",
    "XVII - Word Bearers",
    "XVIII - Salamanders",
    "XIX - Raven Guard",
    "XX - Alpha Legion",
    "Anathema Psykana",
    "Legio Custodes",
    "Mechanicum",
    "Questoris Familia",
    "Solar Auxilia",
]
HH_FACTIONS_WITH_BLANK: List[str] = ["— None —", *HH_FACTIONS]


def _faction_index_or_blank(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return 1 + PLACEHOLDER_FACTIONS.index(value)
    except ValueError:
        return 0

# ===================== Database / Models =====================

SQLModel.metadata.clear()

class Player(SQLModel, table=True):
    __tablename__ = "players"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    default_faction: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True

class WeekLock(SQLModel, table=True):
    """Optional: lock a week+system behind a password (for result submissions/edit)."""
    __tablename__ = "week_locks"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    week: str  # DD/MM/YYYY (Wednesday id)
    system: str  # one of SYSTEMS
    password: str


class PublishState(SQLModel, table=True):
    """Per-week/system publish gate for public view."""
    __tablename__ = "publish_state"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    week: str
    system: str
    published: bool = False


class Signup(SQLModel, table=True):
    """Call to Arms responses per player/week/system (multiple signups allowed, latest wins)."""
    __tablename__ = "signups"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    week: str  # DD/MM/YYYY (Wednesday id)
    system: str  # "TOW" | "Horus Heresy"

    # Player link (by name or id); we'll soft-link by player_id + denormalised name for resilience
    player_id: Optional[int] = Field(default=None, index=True)
    player_name: str

    faction: Optional[str] = None
    points: Optional[int] = None  # Army points
    eta: Optional[str] = None     # Estimated time of arrival (free text HH:MM)
    experience: Optional[str] = None  # "New", "Some", "Veteran" (free text OK)
    vibe: Optional[str] = None        # "Casual" | "Competitive"
    standby_ok: bool = False
    tnt_ok: bool = False             # Triumph & Treachery (3-way OK)
    scenario: Optional[str] = None   # "Open Battle" | "Weekly Scenario"
    can_demo: bool = False           # Available to lead a demo for newish people

class Pairing(SQLModel, table=True):
    """Generated weekly pairings per system."""
    __tablename__ = "pairings"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)

    week: str
    system: str

    a_signup_id: int
    b_signup_id: Optional[int] = None  # None => BYE / standby / 3-way pending

    status: str = "pending"  # "pending" | "played" | "cancelled"
    table: Optional[str] = None # Optional table assignment

    a_faction: Optional[str] = None
    b_faction: Optional[str] = None

# ---- Engine ----
@st.cache_resource
def get_engine():
    if DATABASE_URL:
        return create_engine(DATABASE_URL, echo=False, poolclass=NullPool)
    from sqlalchemy import event
    eng = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
    try:
        @event.listens_for(eng, "connect")
        def _pragma(dbapi_connection, connection_record):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.close()
    except Exception:
        pass
    return eng

engine = get_engine()

@st.cache_resource
def init_db():
    SQLModel.metadata.create_all(engine)
    return True

_ = init_db()

# ===================== Utilities / Theme =====================

_DEF_CSS = """
<style>
html, body, .stApp { background: #141414 !important; color: #f0e8d8 !important; }
.block-container { border: 1px solid rgba(200,163,95,.35); border-radius: 14px; padding: 2.2rem 1.0rem 1.25rem; }
.stTabs [aria-selected="true"] { border-bottom: 3px solid #c8a35f !important; }
.stTabs { margin-top: 0.6rem !important; }
.owl-header { position: sticky; top: 0; z-index: 20; background: #141414; padding: .5rem 0 .6rem; box-shadow: 0 2px 10px rgba(0,0,0,.25); }
.owl-spacer { height: .35rem; }
</style>
"""

def apply_theme():
    st.markdown(_DEF_CSS, unsafe_allow_html=True)


def _img_html_from_secret_or_file(primary_url: str, local_names, width: int, alt: str) -> str:
    """Return <img> HTML from a URL or first local file match; empty string if none."""
    src = None
    if primary_url:
        src = primary_url
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for name in local_names:
            p = os.path.join(base_dir, name)
            if os.path.exists(p):
                try:
                    with open(p, 'rb') as f:
                        import base64
                        b64 = base64.b64encode(f.read()).decode()
                    ext = p.lower().split('.')[-1]
                    mime = 'image/png' if ext == 'png' else 'image/jpeg'
                    src = f'data:{mime};base64,{b64}'
                    break
                except Exception:
                    pass
    return f"<img src='{src}' alt='{alt}' width='{width}'/>" if src else ""

def _find_logo_path() -> Optional[str]:
    for name in ["The-Old-World-Logo.png","The-Old-World-Logo.jpg","old_world_logo.png","old_world_logo.jpg"]:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        if os.path.exists(p):
            return p
    return None


def render_header():
    # Build dual images from secrets or local files; if neither found, fall back to existing single-logo logic.
    # TOW candidates include Old World files; HH includes heresy keywords.
    tow_img = _img_html_from_secret_or_file(
        LOGO_TOW_URL,
        ['The-Old-World-Logo.png','The-Old-World-Logo.jpg','old_world_logo.png','old_world_logo.jpg','tow.png','tow.jpg'],
        HEADER_LOGO_WIDTH,
        'The Old World'
    )
    hh_img = _img_html_from_secret_or_file(
        LOGO_HH_URL,
        ['horus_heresy.png','horus_heresy.jpg','hh_logo.png','hh_logo.jpg','heresy.png','heresy.jpg'],
        HEADER_LOGO_WIDTH,
        'Horus Heresy'
    )

    # Fallback to previous single-logo pipeline if neither produced output
    if not (tow_img or hh_img):
        logo_html = ""
        if LOGO_URL:
            logo_html = f"<img src='{LOGO_URL}' alt='Logo' width='{LOGO_WIDTH}'/>"
        else:
            lp = _find_logo_path()
            if lp:
                with open(lp, "rb") as f:
                    import base64
                    encoded = base64.b64encode(f.read()).decode()
                ext = lp.lower().split(".")[-1]
                mime = "image/png" if ext == "png" else "image/jpeg"
                logo_html = f"<img src='data:{mime};base64,{encoded}' alt='Logo' width='{LOGO_WIDTH}'/>"
        header_html = f"{logo_html}"
    else:
        header_html = f"<div style='display:flex;gap:24px;align-items:center;justify-content:center;flex-wrap:wrap'>{tow_img}{hh_img}</div>"

    st.markdown(f"""
<div class='owl-header' style='display:flex;flex-direction:column;align-items:center;gap:.35rem;margin:1.0rem 0 .6rem;'>
  {header_html}
  <h1 style='margin:0;text-align:center'>CALL TO ARMS</h1>
</div>
<div class='owl-spacer'></div>
""", unsafe_allow_html=True)


def uk_date_str(d: date) -> str:
    return d.strftime("%d/%m/%Y")

def week_id_wed(d: date) -> str:
    # Wednesday identifier (DD/MM/YYYY)
    # From Saturday onwards, treat as next week
    if d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        # Jump to next Monday
        d = d + timedelta(days=7 - d.weekday())

    offset = 2 - d.weekday()  # 2 = Wednesday
    wednesday = d + timedelta(days=offset)
    return uk_date_str(wednesday)

def parse_week_id(week_str: str) -> date:
    """Parse a week identifier like 'DD/MM/YYYY' into a date."""
    return datetime.strptime(week_str.strip(), "%d/%m/%Y").date()


# ---- Cache helpers ----
@st.cache_data(ttl=180)
def player_name_map() -> Dict[int, str]:
    with Session(engine) as s:
        return {p.id: p.name for p in s.exec(select(Player)).all()}

# ===================== Pairing Logic =====================

def _normalize_name(n: str) -> str:
    return " ".join(n.strip().split())

@st.cache_data(ttl=180)
def previous_pairs_recent(system: str, current_week: str, max_weeks: int = 2) -> Set[Tuple[str, str]]:
    """Return unordered player pairs who have played each other within the last `max_weeks` weeks for this system."""
    try:
        current_dt = parse_week_id(current_week)
    except Exception:
        return set()

    with Session(engine) as s:
        out: Set[Tuple[str, str]] = set()
        prs = s.exec(select(Pairing).where(Pairing.system == system)).all()
        for pr in prs:
            if pr.b_signup_id is None:
                continue
            try:
                pr_week_dt = parse_week_id(pr.week)
            except Exception:
                continue
            weeks_apart = abs((current_dt - pr_week_dt).days) // 7
            if weeks_apart > max_weeks:
                continue
            a = s.get(Signup, pr.a_signup_id)
            b = s.get(Signup, pr.b_signup_id)
            if not a or not b:
                continue
            na, nb = _normalize_name(a.player_name).lower(), _normalize_name(b.player_name).lower()
            if na == nb:
                continue
            a1, a2 = sorted([na, nb])
            out.add((a1, a2))
        return out

from dataclasses import dataclass

@dataclass
class MatcherSignup:
    row: Signup
    key: str  # normalized unique key (player name)
    preference: Tuple[int,int,int]  # heuristic tuple for matching

def build_match_preference(su: Signup) -> Tuple[int,int,int]:
    vibe_w = 0 if (su.vibe or "").lower().startswith("casual") else 1
    exp_map = {"new":0, "some":1, "veteran":2, "experienced":2}
    e_key = (su.experience or "").strip().lower()
    exp_w = 1
    for k,v in exp_map.items():
        if k in e_key:
            exp_w = v
            break
    pts = su.points or 0
    pts_bucket = int(round(pts/250.0))
    return (vibe_w, exp_w, pts_bucket)

def generate_pairings_for_week(week: str, system: str, allow_repeats_when_needed: bool = True, allow_tnt: bool = True) -> List[Pairing]:
    with Session(engine) as s:
        # Load candidates
        rows = s.exec(select(Signup).where(
            (Signup.week == week) & (Signup.system == system)
        ).order_by(Signup.created_at)).all()

        # De-duplicate latest signup per player name
        latest_by_name: Dict[str, Signup] = {}
        for r in rows:
            key = _normalize_name(r.player_name).lower()
            # keep most recent per player
            prev = latest_by_name.get(key)
            if (not prev) or (r.created_at > prev.created_at):
                latest_by_name[key] = r

        candidates: List[MatcherSignup] = [
            MatcherSignup(row=v, key=k, preference=build_match_preference(v))
            for k,v in latest_by_name.items()
        ]

        if not candidates:
            return []

        # --- Intro priority pass: match TOW "Intro" seekers with leaders first ---
        intro_pairs: List[Pairing] = []
        used_intro: Set[str] = set()
        if system in ("TOW","Horus Heresy"):
            seekers = [m for m in candidates if (m.row.vibe and m.row.vibe.lower() == "intro")]
            leaders = [m for m in candidates if m.row.can_demo]
            for seeker in seekers:
                if seeker.key in used_intro:
                    continue
                best = None
                best_dist = (99,99,99)
                for lead in leaders:
                    if lead.key in used_intro or lead.key == seeker.key:
                        continue
                    dv = abs(seeker.preference[0] - lead.preference[0])
                    de = abs(seeker.preference[1] - lead.preference[1])
                    dp = abs(seeker.preference[2] - lead.preference[2])
                    dist = (dv, de, dp)
                    if dist < best_dist:
                        best_dist = dist
                        best = lead
                        if dist == (0,0,0):
                            break
                if best is not None:
                    p = Pairing(
                        week=week, system=system,
                        a_signup_id=seeker.row.id, b_signup_id=best.row.id,
                        status="pending",
                        a_faction=seeker.row.faction, b_faction=best.row.faction
                    )
                    s.add(p); s.commit(); s.refresh(p)
                    intro_pairs.append(p)
                    used_intro.add(seeker.key); used_intro.add(best.key)
            candidates = [m for m in candidates if m.key not in used_intro]

        candidates.sort(key=lambda m: (m.preference, m.key))

        seen_pairs = previous_pairs_recent(system, week, max_weeks=2)
        used: Set[str] = set()
        out: List[Pairing] = intro_pairs if "intro_pairs" in locals() else []

        def has_played(x: str, y: str) -> bool:
            a,b = sorted([x,y])
            return (a,b) in seen_pairs

        def _eta_minutes(su):
            try:
                if not su or not su.eta:
                    return None
                hh, mm = str(su.eta).strip().split(":")
                return int(hh) * 60 + int(mm)
            except Exception:
                return None

        def _eta_bucket_diff(a_su, b_su):
            am = _eta_minutes(a_su); bm = _eta_minutes(b_su)
            if am is None or bm is None:
                return 2  # neutral-ish penalty when unknown
            d = abs(am - bm)
            # 0: <=15m, 1: <=30m, 2: <=60m, 3: >60m
            if d <= 15: return 0
            if d <= 30: return 1
            if d <= 60: return 2
            return 3

        def _scenario_diff_tow(a_su, b_su, system_name):
            if system_name != "TOW":
                return 0
            sa = (a_su.scenario or "").strip() if a_su else ""
            sb = (b_su.scenario or "").strip() if b_su else ""
            if not sa or not sb:
                return 1  # slight penalty if one is unknown
            return 0 if sa == sb else 1

        def _mirror_flag(a_su, b_su):
            fa = (a_su.faction or "").strip().lower() if a_su and a_su.faction else ""
            fb = (b_su.faction or "").strip().lower() if b_su and b_su.faction else ""
            if fa and fb and fa == fb:
                return 1  # avoid mirror if possible
            return 0

        def _vibe_distance_override(a_row, b_row, base_dv):
            """Make 'Either' match anything except Intro. Intro remains a separate pre-pass."""
            av = ((getattr(a_row, "vibe", None) or "").strip().lower())
            bv = ((getattr(b_row, "vibe", None) or "").strip().lower())

            # Intro is always authoritative — do not override
            if av == "intro" or bv == "intro":
                return base_dv

            # If either selected 'Either' → no vibe penalty
            if av == "either" or bv == "either":
                return 0

            # Otherwise fallback to normal check
            return 0 if av == bv else 1

        for i, ms in enumerate(candidates):
            if ms.key in used:
                continue
            # find best candidate not used, minimal "distance"
            best_j = None
            best_dist = (99,99,99)  # lexicographic over (vibe, exp, points)
            for j in range(i+1, len(candidates)):
                other = candidates[j]
                if other.key in used:
                    continue
                # avoid rematch if we can
                if has_played(ms.key, other.key):
                    continue
                # distance over preference tuple
                dv_base = abs(ms.preference[0] - other.preference[0])
                dv = _vibe_distance_override(ms.row, other.row, dv_base)
                de = abs(ms.preference[1] - other.preference[1])
                dp = abs(ms.preference[2] - other.preference[2])
                dist = (dv, de, dp)
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
                    # early perfect break
                    if dist == (0,0,0):
                        break
            # if no non-rematch found, allow a rematch if permitted
            if best_j is None and allow_repeats_when_needed:
                for j in range(i+1, len(candidates)):
                    other = candidates[j]
                    if other.key in used:
                        continue
                    # still avoid very recent rematches (within the configured recent window)
                    if has_played(ms.key, other.key):
                        continue
                    dv_base = abs(ms.preference[0] - other.preference[0])
                    dv = _vibe_distance_override(ms.row, other.row, dv_base)
                    de = abs(ms.preference[1] - other.preference[1])
                    dp = abs(ms.preference[2] - other.preference[2])
                    
                    eta_b = _eta_bucket_diff(ms.row, other.row)
                    scen_d = _scenario_diff_tow(ms.row, other.row, system)
                    mir = _mirror_flag(ms.row, other.row)
                    dist = (dv, de, dp)
                    if dist < best_dist:
                        best_dist = dist
                        best_j = j
                        if dist == (0,0,0):
                            break
            if best_j is None:
                # leave as BYE / potential T&T grouping
                p = Pairing(
                    week=week, system=system,
                    a_signup_id=ms.row.id, b_signup_id=None,
                    status="pending",
                    a_faction=ms.row.faction, b_faction=None
                )
                s.add(p); s.commit(); s.refresh(p); out.append(p)
                used.add(ms.key)
            else:
                other = candidates[best_j]
                p = Pairing(
                    week=week, system=system,
                    a_signup_id=ms.row.id, b_signup_id=other.row.id,
                    status="pending",
                    a_faction=ms.row.faction, b_faction=other.row.faction
                )
                s.add(p); s.commit(); s.refresh(p); out.append(p)
                used.add(ms.key); used.add(other.key)

        return out

# ===================== UI =====================

apply_theme()
render_header()

# ---- Sidebar: Access & quick links ----
with st.sidebar:
    st.header("Access")
    if not st.session_state.is_admin:
        with st.form("admin_unlock_form"):
            pw = st.text_input("Admin password", type="password")
            submitted = st.form_submit_button("Unlock admin", use_container_width=True)
        if submitted:
            if pw == ADMIN_PASSWORD:
                st.session_state.is_admin = True
                st.success("Admin mode unlocked."); st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        st.success("Admin mode active")
        if st.button("Lock", use_container_width=True):
            st.session_state.is_admin = False
            st.rerun()
        # DB download if SQLite
        if not DATABASE_URL and os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "rb") as f:
                    data = f.read()
                st.download_button("Download DB", data=data, file_name=DB_PATH, mime="application/octet-stream", use_container_width=True)
            except Exception:
                pass

    st.divider()
    # Element Games (logo centered)
    eg_img = _img_html_from_secret_or_file(ELEMENT_LOGO_URL, ['element_games.png','elementgames.png'], 200, 'Element Games')
    if ELEMENT_URL and eg_img:
        st.markdown(f"<div style='display:flex;justify-content:center;align-items:center;margin-top:8px;margin-bottom:0px'><a href='{ELEMENT_URL}' target='_blank' rel='noopener'>{eg_img}</a></div>", unsafe_allow_html=True)
    elif eg_img:
        st.markdown(f"<div style='display:flex;justify-content:center;align-items:center;margin-top:8px;margin-bottom:0px'>{eg_img}</div>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;opacity:.85;margin-top:6px;margin-bottom:16px'><em>Venue Partner</em></div>", unsafe_allow_html=True)

    # Discord big button (image centered)
    disc_img = _img_html_from_secret_or_file(DISCORD_LOGO_URL, ['discord_button.png','discord.png','discord_logo.png'], 220, 'Join us on Discord')
    if DISCORD_URL and disc_img:
        st.markdown(f"<div style='display:flex;justify-content:center;align-items:center;margin-top:10px'><a href='{DISCORD_URL}' target='_blank' rel='noopener'>{disc_img}</a></div>", unsafe_allow_html=True)
    elif disc_img:
        st.markdown(f"<div style='display:flex;justify-content:center;align-items:center;margin-top:10px'>{disc_img}</div>", unsafe_allow_html=True)

tabs_public = ["Call to Arms", "Pairings"]
tabs_admin  = ["Signups", "Generate Pairings", "Weekly Pairings", "View History"]
order = tabs_public + (tabs_admin if st.session_state.get("is_admin") else [])
T = st.tabs(order)
idx = {name:i for i,name in enumerate(order)}

# --------------- Public: Call to Arms ---------------
with T[idx["Call to Arms"]]:
    st.subheader("Join this week's games")

    # default week id = this week's Wednesday
    week_default = week_id_wed(date.today())
    c1, c2 = st.columns([2,1])
    with c1:
        week_val = st.text_input("Week (Wednesday id, DD/MM/YYYY)", value=week_default, help="We use the Wednesday of the week as the ID.")
    with c2:
        system = st.selectbox("System", SYSTEMS, index=0)

    st.divider()
    # --- Player pick or create (first+last only) ---
    with Session(engine) as _s_pl:
        _players_all = _s_pl.exec(select(Player).order_by(Player.id)).all()

    def _fmt_player_label(p):
        nm = (getattr(p, "name", "") or "").strip()
        return f"#{p.id} — {nm or 'Unnamed'}"

    _player_labels = [_fmt_player_label(p) for p in _players_all]
    _label_to_id = { _fmt_player_label(p): p.id for p in _players_all }

    st.markdown("### Who are you?")
    _is_new = st.checkbox("I'm new (create a player profile)")

    selected_player_label = None
    first = ""
    last = ""

    with st.form("signup_form", clear_on_submit=True):
        is_hh = (system == "Horus Heresy")
        name_ph = "e.g., Alpharius" if is_hh else "e.g., Heinrich Kemmler"

        if not _is_new:
            selected_player_label = st.selectbox(
                "Select your player",
                options=(['— Select —'] + _player_labels),
                index=0,
                placeholder="Type to search…"
            )
        else:
            _cfa, _cfb = st.columns(2)
            with _cfa:
                first = st.text_input("First name *")
            with _cfb:
                last = st.text_input("Last name *")
        # Factions
        if is_hh:
            faction_choice = st.selectbox("Your faction", HH_FACTIONS_WITH_BLANK, index=0)
        else:
            faction_choice = st.selectbox("Your faction", PLACEHOLDER_FACTIONS_WITH_BLANK, index=0)
        # Points
        default_pts = 3000 if is_hh else 2000
        pts = st.number_input("Army points", min_value=0, max_value=10000, value=default_pts, step=50)
        # ETA dropdown 17:00-19:30
        eta_options = []
        for h in [17,18,19]:
            for m in [0,15,30,45]:
                if h == 19 and m > 30:
                    continue
                eta_options.append(f"{h:02d}:{m:02d}")
        eta_default_idx = eta_options.index("18:30") if "18:30" in eta_options else 0
        eta = st.selectbox("Estimated time of arrival", eta_options, index=eta_default_idx)
        exp = st.selectbox("Experience", ["New", "Some", "Veteran"])
        # Type of game
        if is_hh:
            vibe = st.selectbox("Type of game", ["Standard", "Intro", "Either"])
        else:
            vibe = st.selectbox("Type of game", ["Casual", "Competitive", "Intro", "Either"])
        standby = st.checkbox("I can be on standby", value=False)
        # Triumph & Treachery (TOW only)
        if not is_hh:
            tnt = st.checkbox("I can play Triumph & Treachery (3-way)", value=False)
        else:
            tnt = False
        # Scenario (TOW only)
        if not is_hh:
            scenario = st.selectbox("Scenario preference", ["Open Battle", "Weekly Scenario"])
        else:
            scenario = None
        can_demo = st.checkbox("I can lead an intro game", value=False)

        submitted = st.form_submit_button("Submit")

    if submitted:
        with Session(engine) as s:
            pl = None
            if not _is_new:
                if selected_player_label and selected_player_label in _label_to_id:
                    pl = s.get(Player, _label_to_id[selected_player_label])
                else:
                    st.error("Please select your player from the list, or tick 'I'm new' and enter your name.")
                    st.stop()
            else:
                if not first.strip() or not last.strip():
                    st.error("Please enter both first and last name.")
                    st.stop()
                full_name = f"{first.strip()} {last.strip()}"
                pl = s.exec(select(Player).where(Player.name.ilike(full_name))).first()
                if not pl:
                    pl = Player(name=full_name, default_faction=None, active=True)
                    s.add(pl); s.commit(); s.refresh(pl)

            faction = None if faction_choice == "— None —" else faction_choice

            su = Signup(
                week=week_val.strip(), system=system,
                player_id=pl.id, player_name=pl.name,
                faction=faction, points=int(pts), eta=eta.strip() or None,
                experience=exp, vibe=vibe,
                standby_ok=standby, tnt_ok=tnt,
                scenario=scenario, can_demo=can_demo
            )
            s.add(su); s.commit()
        st.success("Thanks! You're on the list.")


# --------------- Public: Pairings view ---------------
with T[idx["Pairings"]]:
    st.subheader("Weekly Pairings")
    week_lookup = st.text_input("Week (DD/MM/YYYY)", value=week_id_wed(date.today()))
    sys_pick = st.selectbox("System", SYSTEMS, index=0, key="pub_sys")

    # Only show when published
    with Session(engine) as s:
        gate = s.exec(select(PublishState).where((PublishState.week == week_lookup) & (PublishState.system == sys_pick))).first()

    if not gate or not gate.published:
        st.info("No pairings published yet for this week/system.")
    else:
        with Session(engine) as s:
            prs = s.exec(select(Pairing).where((Pairing.week == week_lookup) & (Pairing.system == sys_pick)).order_by(Pairing.id)).all()
        if not prs:
            st.info("No pairings yet.")
        else:
            with Session(engine) as s:

                def _public_vibe_display(a_v, b_v):
                    av = (a_v or "").strip()
                    bv = (b_v or "").strip()
                    av_l = av.lower()
                    bv_l = bv.lower()

                    if av_l == "intro" or bv_l == "intro":
                        return "Intro"

                    if av_l == "either" and bv:
                        return bv

                    if bv_l == "either" and av:
                        return av

                    if av_l == "either" and bv_l == "either":
                        return "Either"

                    return av or bv or ""

                rows = []
                for p in prs:
                    a = s.get(Signup, p.a_signup_id)
                    b = s.get(Signup, p.b_signup_id) if p.b_signup_id else None

                    # Compute ETA (later of two) and Points (lower of two)
                    def _parse_eta(sval):
                        if not sval:
                            return None
                        try:
                            from datetime import datetime
                            return datetime.strptime(str(sval).strip(), "%H:%M").time()
                        except Exception:
                            return None

                    ta = _parse_eta(a.eta if a else None)
                    tb = _parse_eta(b.eta if b else None)
                    if ta and tb:
                        eta_show = max(ta, tb).strftime("%H:%M")
                    elif ta:
                        eta_show = ta.strftime("%H:%M")
                    elif tb:
                        eta_show = tb.strftime("%H:%M")
                    else:
                        eta_show = None

                    pts_vals = []
                    if a and isinstance(a.points, int):
                        pts_vals.append(a.points)
                    if b and isinstance(b.points, int):
                        pts_vals.append(b.points)
                    pts_show = min(pts_vals) if pts_vals else None

                    rows.append({
                        "A": a.player_name if a else f"A#{p.a_signup_id}",
                        "Faction A": p.a_faction or (a.faction if a else None),
                        "B": (b.player_name if b else "— BYE / standby —"),
                        "Faction B": (p.b_faction or (b.faction if b else None) if b else None),
                        "Type": _public_vibe_display(getattr(a, "vibe", None), getattr(b, "vibe", None)),
                        "ETA": eta_show,
                        "Points": pts_show
                    })
            st.dataframe(rows, use_container_width=True, hide_index=True)

# --------------- Admin: Signups ---------------
if "Signups" in idx:
    with T[idx["Signups"]]:
        st.subheader("Browse Signups")
        week_lookup = st.text_input("Week", value=week_id_wed(date.today()), key="adm_week_su")
        sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_sys_su")
        with Session(engine) as s:
            sus = s.exec(select(Signup).where((Signup.week == week_lookup) & (Signup.system == sys_pick)).order_by(Signup.created_at)).all()
        if not sus:
            st.info("No signups yet.")
        else:
            import pandas as pd
            rows = [{
                "ID": su.id,
                "Name": su.player_name,
                "Faction": su.faction,
                "Pts": su.points,
                "ETA": su.eta,
                "Exp": su.experience,
                "Type": su.vibe,
                "Standby": su.standby_ok,
                "T&T": su.tnt_ok,
                "Scenario": su.scenario,
                "Can lead intro": su.can_demo,
                "Created": su.created_at.strftime("%Y-%m-%d %H:%M")
            } for su in sus]
            df = pd.DataFrame(rows)
            # Make certain columns non-editable
            disabled_cols = ["ID", "Name", "Created"]
            edited = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                disabled=disabled_cols,
                key="signups_editor"
            )
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Save changes"):
                    # Compare and persist changes back to DB
                    changes = 0
                    orig_map = {r["ID"]: r for r in rows}
                    with Session(engine) as s:
                        for _, r in edited.iterrows():
                            rid = int(r["ID"])
                            o = orig_map[rid]
                            fields = ["Faction","Pts","ETA","Exp","Type","Standby","T&T","Scenario","Can lead intro"]
                            if any(r[f] != o[f] for f in fields):
                                su = s.get(Signup, rid)
                                if su:
                                    su.faction = r["Faction"] if pd.notna(r["Faction"]) else None
                                    su.points = int(r["Pts"]) if pd.notna(r["Pts"]) else None
                                    su.eta = str(r["ETA"]) if pd.notna(r["ETA"]) else None
                                    su.experience = r["Exp"] if pd.notna(r["Exp"]) else None
                                    su.vibe = r["Type"] if pd.notna(r["Type"]) else None
                                    su.standby_ok = bool(r["Standby"]) if pd.notna(r["Standby"]) else False
                                    su.tnt_ok = bool(r["T&T"]) if pd.notna(r["T&T"]) else False
                                    su.scenario = r["Scenario"] if pd.notna(r["Scenario"]) else None
                                    su.can_demo = bool(r["Can lead intro"]) if pd.notna(r["Can lead intro"]) else False
                                    s.add(su); changes += 1
                        if changes:
                            s.commit()
                    if changes:
                        st.success(f"Saved {changes} row(s).")
                    else:
                        st.info("No changes detected.")
            with c2:
                del_ids = st.multiselect("Delete signups (select ID)", options=list(edited["ID"]))
                if st.button("Delete selected") and del_ids:
                    with Session(engine) as s:
                        for rid in del_ids:
                            obj = s.get(Signup, int(rid))
                            if obj:
                                s.delete(obj)
                        s.commit()
                    st.warning(f"Deleted {len(del_ids)} signup(s).")

# --------------- Admin: Generate ---------------
if "Generate Pairings" in idx:
    with T[idx["Generate Pairings"]]:
        st.subheader("Generate Weekly Pairings")
        c1, c2 = st.columns([2,1])
        with c1:
            week_val = st.text_input("Week id", value=week_id_wed(date.today()), key="adm_week_gen")
        with c2:
            sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_sys_gen")

        st.caption("Deletes existing **pending** pairings for that week+system before generating.")
        allow_repeats = st.checkbox("Allow rematches if necessary", value=True)
        allow_tnt = st.checkbox("Enable 3-way (T&T) grouping when odd numbers", value=True, help="Creates a BYE record for the odd person; you can manually combine into a 3-way below.")

        if st.button("Generate pairings", type="primary"):
            with Session(engine) as s:
                # Clear existing pending for this week+system
                old = s.exec(select(Pairing).where((Pairing.week == week_val) & (Pairing.system == sys_pick) & (Pairing.status == "pending"))).all()
                for r in old:
                    s.delete(r)
                s.commit()
            created = generate_pairings_for_week(week_val, sys_pick, allow_repeats_when_needed=allow_repeats, allow_tnt=allow_tnt)
            if created:
                st.success(f"Created {len(created)} pairing(s).")
            else:
                st.info("No signups to pair.")

        st.divider(); st.subheader("Manual 3-way merge (optional)")
        with Session(engine) as s:
            prs = s.exec(select(Pairing).where((Pairing.week == week_val) & (Pairing.system == sys_pick)).order_by(Pairing.id)).all()
            all_su = {su.id: su for su in s.exec(select(Signup).where((Signup.week == week_val) & (Signup.system == sys_pick))).all()}
        if prs:
            labels = []
            id_map = {}
            for p in prs:
                a = all_su.get(p.a_signup_id)
                b = all_su.get(p.b_signup_id) if p.b_signup_id else None
                label = f"#{p.id}: {(a.player_name if a else 'A?')} vs {(b.player_name if b else 'BYE')}"
                labels.append(label); id_map[label] = p.id
            bye_labels = []
            bye_id_map = {}
            for p in prs:
                if p.b_signup_id is None:
                    a = all_su.get(p.a_signup_id)
                    bye_labels.append(f"BYE #{p.id}: {(a.player_name if a else 'A?')}")
                    bye_id_map[bye_labels[-1]] = p.id
            if len(bye_labels) >= 2 and labels:
                with st.form("merge_tnt_form"):
                    b1 = st.selectbox("BYE 1", options=bye_labels, key="bye1")
                    b2 = st.selectbox("BYE 2", options=[x for x in bye_labels if x != b1], key="bye2")
                    host = st.selectbox("Host pairing (will become 3-way)", options=labels, key="host_sel")
                    do_merge = st.form_submit_button("Merge into 3-way")
                if do_merge:
                    with Session(engine) as s:
                        host_id = id_map[host]
                        p_host = s.get(Pairing, host_id)
                        p_b1 = s.get(Pairing, bye_id_map[b1])
                        p_b2 = s.get(Pairing, bye_id_map[b2])
                        if p_host and p_b1 and p_b2 and p_host.b_signup_id is not None:
                            p_b1.status = "cancelled"
                            p_b2.status = "cancelled"
                            s.add(p_b1); s.add(p_b2)
                            s.commit()
                            st.success("Merged (logical). Please coordinate 3-way among the three players.")
                        else:
                            st.error("Pick a host that already has two players.")
            else:
                st.info("Need at least two BYE entries to propose a 3-way merge.")
        else:
            st.info("No pairings yet for that week/system.")


# --------------- Admin: Pairings ---------------
if "Weekly Pairings" in idx:
    with T[idx["Weekly Pairings"]]:
        st.subheader("Browse / Delete Pairings")
        week_lookup = st.text_input("Week", value=week_id_wed(date.today()), key="adm_week_pairs")
        sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_sys_pairs")

        # Publish controls
        with Session(engine) as s:
            gate = s.exec(select(PublishState).where((PublishState.week == week_lookup) & (PublishState.system == sys_pick))).first()
        col_p1, col_p2, col_p3 = st.columns([1,1,3])
        with col_p1:
            if st.button("Publish to Public"):
                with Session(engine) as s:
                    g = s.exec(select(PublishState).where((PublishState.week == week_lookup) & (PublishState.system == sys_pick))).first()
                    if not g:
                        g = PublishState(week=week_lookup, system=sys_pick, published=True)
                    else:
                        g.published = True
                    s.add(g); s.commit()
                st.success("Published.")
                st.rerun()
        with col_p2:
            if st.button("Unpublish"):
                with Session(engine) as s:
                    g = s.exec(select(PublishState).where((PublishState.week == week_lookup) & (PublishState.system == sys_pick))).first()
                    if not g:
                        g = PublishState(week=week_lookup, system=sys_pick, published=False)
                    else:
                        g.published = False
                    s.add(g); s.commit()
                st.warning("Unpublished.")
                st.rerun()
        with col_p3:
            st.caption(f"Public status: **{'Published' if (gate and gate.published) else 'Not Published'}**")

        with Session(engine) as s:
            prs = s.exec(select(Pairing).where((Pairing.week == week_lookup) & (Pairing.system == sys_pick)).order_by(Pairing.id)).all()
        if not prs:
            st.info("No pairings.")
        else:
            with Session(engine) as s:
                rows = []
                for p in prs:
                    a = s.get(Signup, p.a_signup_id)
                    b = s.get(Signup, p.b_signup_id) if p.b_signup_id else None

                    # Compute ETA (later of two) and Points (lower of two)
                    def _parse_eta_admin(sval):
                        if not sval:
                            return None
                        try:
                            from datetime import datetime
                            return datetime.strptime(str(sval).strip(), "%H:%M").time()
                        except Exception:
                            return None

                    ta = _parse_eta_admin(a.eta if a else None)
                    tb = _parse_eta_admin(b.eta if b else None)
                    if ta and tb:
                        eta_show = max(ta, tb).strftime("%H:%M")
                    elif ta:
                        eta_show = ta.strftime("%H:%M")
                    elif tb:
                        eta_show = tb.strftime("%H:%M")
                    else:
                        eta_show = None

                    pts_vals = []
                    if a and isinstance(a.points, int):
                        pts_vals.append(a.points)
                    if b and isinstance(b.points, int):
                        pts_vals.append(b.points)
                    pts_show = min(pts_vals) if pts_vals else None

                    rows.append({
                        "ID": p.id,
                        "A": a.player_name if a else f"A#{p.a_signup_id}",
                        "A Faction": (p.a_faction or (a.faction if a else None)),
                        "A Type": (a.vibe if a else None),
                        "B": (b.player_name if b else "BYE"),
                        "B Faction": ((p.b_faction or (b.faction if b else None)) if b else None),
                        "B Type": ((b.vibe if b else None) if b else None),
                        "Status": p.status,
                        "ETA": eta_show,
                        "Points": pts_show
                    })
            st.dataframe(rows, use_container_width=True, hide_index=True)
            with st.form("delete_pairs_form", clear_on_submit=True):
                ids_str = st.text_input("Delete pairing IDs (comma-separated)")
                do_delete = st.form_submit_button("Delete selected")
            if do_delete and ids_str.strip():
                try:
                    ids = [int(x.strip()) for x in ids_str.split(",") if x.strip().isdigit()]
                    with Session(engine) as s:
                        for pid in ids:
                            obj = s.get(Pairing, pid)
                            if obj:
                                s.delete(obj)
                        s.commit()
                    st.success(f"Deleted {len(ids)} pairing(s).")
                except Exception as e:
                    st.error(f"Error: {e}")


# --------------- Admin: View History ---------------
if "View History" in idx:
    with T[idx["View History"]]:
        st.subheader("View History")
        sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_hist_sys")
        week_filter = st.text_input("Week contains (optional)", value="", key="adm_hist_week_filter")
        limit = st.number_input("Show last N pairings", min_value=10, max_value=1000, value=200, step=10, help="Caps how many rows to display")

        with Session(engine) as s:
            q = select(Pairing).where(Pairing.system == sys_pick)
            if week_filter.strip():
                # ilike for case-insensitive substring match on week id
                q = q.where(Pairing.week.ilike(f"%{week_filter.strip()}%"))
            prs = s.exec(q.order_by(Pairing.week.desc(), Pairing.id.desc())).all()

        if not prs:
            st.info("No historical pairings match your filters.")
        else:
            with Session(engine) as s:
                rows = []
                def _parse_eta_hist(sval):
                    if not sval:
                        return None
                    try:
                        from datetime import datetime
                        return datetime.strptime(str(sval).strip(), "%H:%M").time()
                    except Exception:
                        return None

                for p in prs[:limit]:
                    a = s.get(Signup, p.a_signup_id)
                    b = s.get(Signup, p.b_signup_id) if p.b_signup_id else None

                    ta = _parse_eta_hist(a.eta if a else None)
                    tb = _parse_eta_hist(b.eta if b else None)
                    if ta and tb:
                        eta_show = max(ta, tb).strftime("%H:%M")
                    elif ta:
                        eta_show = ta.strftime("%H:%M")
                    elif tb:
                        eta_show = tb.strftime("%H:%M")
                    else:
                        eta_show = None

                    pts_vals = []
                    if a and isinstance(a.points, int):
                        pts_vals.append(a.points)
                    if b and isinstance(b.points, int):
                        pts_vals.append(b.points)
                    pts_show = min(pts_vals) if pts_vals else None

                    rows.append({
                        "ID": p.id,
                        "Week": p.week,
                        "System": p.system,
                        "A": a.player_name if a else f"A#{p.a_signup_id}",
                        "A Faction": (p.a_faction or (a.faction if a else None)),
                        "A Type": (a.vibe if a else None),
                        "B": (b.player_name if b else ("BYE" if p.b_signup_id is None else f"B#{p.b_signup_id}")),
                        "B Faction": ((p.b_faction or (b.faction if b else None)) if b else None),
                        "B Type": ((b.vibe if b else None) if b else None),
                        "Status": p.status,
                        "Table": p.table,
                        "ETA": eta_show,
                        "Points": pts_show,
                    })

            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download history as CSV", data=csv, file_name="pairings_history.csv", mime="text/csv", use_container_width=True)
