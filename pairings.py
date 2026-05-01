"""
Call to Arms
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Literal, Optional, Set, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import requests
from table2ascii import table2ascii as t2a, PresetStyle

import streamlit as st

def _get_secret(name: str, default=None):
    """Safe secret getter: uses st.secrets when available, else falls back to environment variables.
    This keeps non-Streamlit contexts (e.g. GitHub Actions) from crashing when importing this module.
    """
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)


from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy.pool import NullPool

# ===================== Config & State =====================

st.set_page_config(page_title="Call to Arms — Pairings", layout="wide")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

ADMIN_PASSWORD = _get_secret("ADMIN_PASSWORD", "change-me")
LOGO_URL = _get_secret("LOGO_URL", "")
LOGO_WIDTH = int(_get_secret("LOGO_WIDTH", 120))
DATABASE_URL = _get_secret("DATABASE_URL")  # optional (Postgres); default local SQLite
DB_PATH = "pairings_db.sqlite"
LOGO_TOW_URL = _get_secret("TOW_LOGO_URL", "")
LOGO_HH_URL = _get_secret("HH_LOGO_URL", "")
LOGO_KT_URL = _get_secret("KT_LOGO_URL", "")
HEADER_LOGO_WIDTH = int(_get_secret("HEADER_LOGO_WIDTH", 120))
ELEMENT_URL = _get_secret("ELEMENT_URL", "")
ELEMENT_LOGO_URL = _get_secret("ELEMENT_LOGO_URL", "")
DISCORD_URL = _get_secret("DISCORD_URL", "")
DISCORD_LOGO_URL = _get_secret("DISCORD_LOGO_URL", "")
DISCORD_SIGNUP_WEBHOOK_URL = _get_secret("DISCORD_SIGNUP_WEBHOOK_URL", "")
DISCORD_CALL_TO_ARMS_WEBHOOK_URL = _get_secret("DISCORD_CALL_TO_ARMS_WEBHOOK_URL", "")
DISCORD_PAIRINGS_WEBHOOK_URL = _get_secret("DISCORD_PAIRINGS_WEBHOOK_URL", "")
SYSTEMS: List[str] = ["The Old World", "The Horus Heresy", "Kill Team"]
TNT_SUGGESTIONS = {}
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

# Kill Team factions
KT_FACTIONS: List[str] = [
    "Angels Of Death",
    "Battleclade",
    "Blades Of Khaine",
    "Blooded",
    "Brood Brothers",
    "Canoptek Circle",
    "Celestian Insidiants",
    "Chaos Cult",
    "Corsair Voidscarred",
    "Death Korps",
    "Deathwatch",
    "Elucidian Starstriders",
    "Exaction Squad",
    "Farstalker Kinband",
    "Fellgor Ravagers",
    "Gellerpox Infected",
    "Goremongers",
    "Hand Of The Archon",
    "Hearthkyn Salvagers",
    "Hernkyn Yaegirs",
    "Hierotek Circle",
    "Hunter Clade",
    "Imperial Navy Breachers",
    "Inquisitorial Agents",
    "Kasrkin",
    "Kommandos",
    "Legionaries",
    "Mandrakes",
    "Murderwing",
    "Nemesis Claw",
    "Novitiates",
    "Pathfinders",
    "Phobos Strike Team",
    "Plague Marines",
    "Ratlings",
    "Raveners",
    "Sanctifiers",
    "Scout Squad",
    "Strike Force Variel",
    "Tempestus Aquilon",
    "Vespid Stingwings",
    "Void-Dancer Troupe",
    "Warp Coven",
    "Wolf Scouts",
    "Wrecka Krew",
    "Wyrmblade",
    "XV26 Stealth Battlesuits",
]
KT_FACTIONS_WITH_BLANK: List[str] = ["— None —", *KT_FACTIONS]


# --- TOW Weekly Scenario Pool -------------------------------------------------

COMMON_OBJECTIVES_TOW = "Dead or Fled, The King is Dead, Trophies of War"

TOW_SCENARIOS = [
    {
        "code": "1a",
        "name": "Upon the Field of Glory",
        "secondary_objectives": "Baggage Train, Strategic Locations (2), Special Features",
        "terrain_path": "missions/1a.png",
    },
    {
        "code": "1b",
        "name": "Upon the Field of Glory",
        "secondary_objectives": "Baggage Train, Strategic Locations (4)",
        "terrain_path": "missions/1b.png",
    },
    {
        "code": "1c",
        "name": "Upon the Field of Glory",
        "secondary_objectives": "Baggage Train, Strategic Locations (3), Domination",
        "terrain_path": "missions/1c.png",
    },

    {
        "code": "2a",
        "name": "King of the Hill",
        "secondary_objectives": "Baggage Train",
        "terrain_path": "missions/2a.png",
    },
    {
        "code": "2b",
        "name": "King of the Hill",
        "secondary_objectives": "Baggage Train, Special Features",
        "terrain_path": "missions/2b.png",
    },
    {
        "code": "2c",
        "name": "King of the Hill",
        "secondary_objectives": "Baggage Train",
        "terrain_path": "missions/2c.png",
    },

    {
        "code": "3a",
        "name": "Drawn Battlelines",
        "secondary_objectives": "Baggage Train, Strategic Locations (3)",
        "terrain_path": "missions/3a.png",
    },
    {
        "code": "3b",
        "name": "Drawn Battlelines",
        "secondary_objectives": "Baggage Train, Strategic Locations (3)",
        "terrain_path": "missions/3b.png",
    },
    {
        "code": "3c",
        "name": "Drawn Battlelines",
        "secondary_objectives": "Baggage Train, Strategic Locations (3)",
        "terrain_path": "missions/3c.png",
    },

    {
        "code": "4a",
        "name": "Close Quarter",
        "secondary_objectives": "Strategic Locations (2)",
        "terrain_path": "missions/4a.png",
    },
    {
        "code": "4b",
        "name": "Close Quarter",
        "secondary_objectives": "Strategic Locations (2)",
        "terrain_path": "missions/4b.png",
    },
    {
        "code": "4c",
        "name": "Close Quarter",
        "secondary_objectives": "Strategic Locations (2)",
        "terrain_path": "missions/4c.png",
    },

    {
        "code": "5a",
        "name": "A Chance Encounter",
        "secondary_objectives": "Special Features",
        "terrain_path": "missions/5a.png",
    },
    {
        "code": "5b",
        "name": "A Chance Encounter",
        "secondary_objectives": "Special Features, Domination",
        "terrain_path": "missions/5b.png",
    },
    {
        "code": "5c",
        "name": "A Chance Encounter",
        "secondary_objectives": "Special Features",
        "terrain_path": "missions/5c.png",
    },

    {
        "code": "6a",
        "name": "Encirclement",
        "secondary_objectives": "Baggage Train, Special Features, Strategic Locations (4)",
        "terrain_path": "missions/6a.png",
    },
    {
        "code": "6b",
        "name": "Encirclement",
        "secondary_objectives": "Baggage Train, Special Features",
        "terrain_path": "missions/6b.png",
    },
    {
        "code": "6c",
        "name": "Encirclement",
        "secondary_objectives": "Special Features, Strategic Locations (4)",
        "terrain_path": "missions/6c.png",
    },
]


def _faction_index_or_blank(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return 1 + PLACEHOLDER_FACTIONS.index(value)
    except ValueError:
        return 0

# ===================== Database / Models =====================


def _public_vibe_display(a_v, b_v):
    """Decide the public-facing 'Type' string for a pairing, respecting Intro/Either semantics."""
    av = (a_v or "").strip()
    bv = (b_v or "").strip()
    av_l = av.lower()
    bv_l = bv.lower()

    # Intro overrides everything
    if av_l == "intro" or bv_l == "intro":
        return "Intro"

    # Both 'Either' → show 'Either'
    if av_l == "either" and bv_l == "either":
        return "Either"

    # 'Either' adopts the other player's vibe
    if av_l == "either" and bv:
        return bv
    if bv_l == "either" and av:
        return av

    # Otherwise prefer A's vibe, falling back to B's, then blank
    return av or bv or ""


SQLModel.metadata.clear()

class Player(SQLModel, table=True):
    __tablename__ = "players"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    default_faction: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True

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

    week: str  # DD/MM/YYYY (system game-day id; TOW = Wed, HH = Fri)
    system: str  # "The Old World" | "The Horus Heresy"

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

class LeagueResult(SQLModel, table=True):
    """Submitted Old World League game results, separate from weekly pairings."""
    __tablename__ = "league_results"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    player_1_id: Optional[int] = Field(default=None, index=True)
    player_1_name: str
    player_2_id: Optional[int] = Field(default=None, index=True)
    player_2_name: str
    result: str
    result_date: str
    player_1_faction: Optional[str] = None
    player_2_faction: Optional[str] = None
    player_1_painting_bonus: Optional[str] = None
    player_2_painting_bonus: Optional[str] = None
    game_type: str = "Competitive"  # "Casual" => K=10; "Competitive" => K=40

    # ELO snapshots. These are recalculated from full league history whenever
    # results are added/deleted, so corrections stay consistent.
    player_1_rating_before: Optional[float] = None
    player_2_rating_before: Optional[float] = None
    player_1_rating_after: Optional[float] = None
    player_2_rating_after: Optional[float] = None
    k_factor_used: Optional[int] = None

class LeagueRating(SQLModel, table=True):
    """Current Old World League rating, separate from the shared app player profile."""
    __tablename__ = "league_ratings"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    player_id: int = Field(index=True)
    player_name: str
    rating: float = 1000.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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

@st.cache_resource(show_spinner=False)
def ensure_league_results_table() -> None:
    """Ensure league tables/columns exist once per app process.

    create_all creates new tables but does not add new columns to an existing
    table, so this also includes a small league-only migration for SQLite and
    Postgres/Supabase.
    """
    try:
        SQLModel.metadata.create_all(engine, tables=[LeagueResult.__table__, LeagueRating.__table__])
    except Exception:
        pass

    try:
        with engine.connect() as conn:
            is_sqlite = str(engine.url).startswith("sqlite")
            if is_sqlite:
                existing_cols = {r[1] for r in conn.exec_driver_sql('PRAGMA table_info("league_results")').fetchall()}
                sqlite_additions = {
                    "player_1_rating_before": "REAL",
                    "player_2_rating_before": "REAL",
                    "player_1_rating_after": "REAL",
                    "player_2_rating_after": "REAL",
                    "k_factor_used": "INTEGER",
                    "player_1_faction": "TEXT",
                    "player_2_faction": "TEXT",
                    "player_1_painting_bonus": "TEXT",
                    "player_2_painting_bonus": "TEXT",
                    "game_type": "TEXT DEFAULT 'Competitive'",
                }
                for col, col_type in sqlite_additions.items():
                    if col not in existing_cols:
                        conn.exec_driver_sql(f'ALTER TABLE "league_results" ADD COLUMN {col} {col_type}')
            else:
                conn.exec_driver_sql('ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_1_rating_before DOUBLE PRECISION')
                conn.exec_driver_sql('ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_2_rating_before DOUBLE PRECISION')
                conn.exec_driver_sql('ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_1_rating_after DOUBLE PRECISION')
                conn.exec_driver_sql('ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_2_rating_after DOUBLE PRECISION')
                conn.exec_driver_sql('ALTER TABLE league_results ADD COLUMN IF NOT EXISTS k_factor_used INTEGER')
                conn.exec_driver_sql("ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_1_faction TEXT")
                conn.exec_driver_sql("ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_2_faction TEXT")
                conn.exec_driver_sql("ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_1_painting_bonus TEXT")
                conn.exec_driver_sql("ALTER TABLE league_results ADD COLUMN IF NOT EXISTS player_2_painting_bonus TEXT")
                conn.exec_driver_sql("ALTER TABLE league_results ADD COLUMN IF NOT EXISTS game_type TEXT DEFAULT 'Competitive'")
            conn.commit()
    except Exception:
        pass

ensure_league_results_table()

LEAGUE_BASE_RATING = 1000.0
LEAGUE_CASUAL_K_FACTOR = 10
LEAGUE_COMPETITIVE_K_FACTOR = 40

def invalidate_app_caches() -> None:
    """Clear cached read snapshots after database writes so the UI refreshes cleanly."""
    try:
        st.cache_data.clear()
    except Exception:
        pass

def league_expected_score(r_player: float, r_opponent: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_opponent - r_player) / 400.0))

def update_league_elo(r_1: float, r_2: float, score_1: float, k: int) -> Tuple[float, float]:
    e_1 = league_expected_score(r_1, r_2)
    e_2 = league_expected_score(r_2, r_1)
    return r_1 + k * (score_1 - e_1), r_2 + k * ((1 - score_1) - e_2)

def _score_for_player_1(result: str) -> float:
    if result == "Player 1 Victory":
        return 1.0
    if result == "Player 2 Victory":
        return 0.0
    return 0.5

def _league_k_for_game_type(game_type: Optional[str]) -> int:
    return LEAGUE_CASUAL_K_FACTOR if (game_type or "").strip().lower() == "casual" else LEAGUE_COMPETITIVE_K_FACTOR

def _league_painting_bonus_score(painting_bonus: Optional[str]) -> int:
    """Return the flat ELO bonus awarded for league painting status."""
    label = (painting_bonus or "").strip().lower()
    if label == "fully painted":
        return 3
    if label == "partially painted":
        return 1
    return 0

def recalc_league_ratings() -> None:
    """Rebuild Old World League ratings and per-game snapshots from submitted results."""
    ensure_league_results_table()
    with Session(engine) as s:
        results = s.exec(select(LeagueResult).order_by(LeagueResult.id)).all()
        ratings: Dict[int, float] = {}
        names: Dict[int, str] = {}

        for lr in results:
            if lr.player_1_id is None or lr.player_2_id is None:
                continue
            if lr.player_1_id == lr.player_2_id:
                continue

            p1 = int(lr.player_1_id)
            p2 = int(lr.player_2_id)
            names[p1] = lr.player_1_name
            names[p2] = lr.player_2_name
            ratings.setdefault(p1, LEAGUE_BASE_RATING)
            ratings.setdefault(p2, LEAGUE_BASE_RATING)

            before_1 = ratings[p1]
            before_2 = ratings[p2]
            game_type = (getattr(lr, "game_type", None) or "Competitive").strip() or "Competitive"
            k_used = _league_k_for_game_type(game_type)
            after_1, after_2 = update_league_elo(before_1, before_2, _score_for_player_1(lr.result), k_used)

            # Apply painting bonuses as flat additions after the standard ELO equation.
            # "— None —"/blank = 0, Partially Painted = 1, Fully Painted = 3.
            after_1 += _league_painting_bonus_score(getattr(lr, "player_1_painting_bonus", None))
            after_2 += _league_painting_bonus_score(getattr(lr, "player_2_painting_bonus", None))

            lr.game_type = game_type
            lr.player_1_rating_before = before_1
            lr.player_2_rating_before = before_2
            lr.player_1_rating_after = after_1
            lr.player_2_rating_after = after_2
            lr.k_factor_used = k_used

            ratings[p1] = after_1
            ratings[p2] = after_2
            s.add(lr)

        for existing in s.exec(select(LeagueRating)).all():
            s.delete(existing)

        for pid, rating in ratings.items():
            s.add(
                LeagueRating(
                    player_id=pid,
                    player_name=names.get(pid, f"Player #{pid}"),
                    rating=rating,
                    updated_at=datetime.utcnow(),
                )
            )
        s.commit()

    invalidate_app_caches()

@st.cache_data(ttl=600, show_spinner=False)
def _league_faction_and_games_maps() -> Tuple[Dict[int, str], Dict[int, int]]:
    ensure_league_results_table()
    with Session(engine) as s:
        results = s.exec(select(LeagueResult).order_by(LeagueResult.id)).all()

    faction_counts: Dict[int, Dict[str, int]] = {}
    faction_last_seen: Dict[Tuple[int, str], int] = {}
    games_played: Dict[int, int] = {}

    for lr in results:
        row_id = int(lr.id or 0)
        for pid, faction in [
            (lr.player_1_id, getattr(lr, "player_1_faction", None)),
            (lr.player_2_id, getattr(lr, "player_2_faction", None)),
        ]:
            if pid is None:
                continue
            pid_int = int(pid)
            games_played[pid_int] = games_played.get(pid_int, 0) + 1
            faction_clean = (faction or "").strip()
            if not faction_clean:
                continue
            pid_factions = faction_counts.setdefault(pid_int, {})
            pid_factions[faction_clean] = pid_factions.get(faction_clean, 0) + 1
            faction_last_seen[(pid_int, faction_clean)] = max(faction_last_seen.get((pid_int, faction_clean), 0), row_id)

    faction_map: Dict[int, str] = {}
    for pid, facs in faction_counts.items():
        faction_map[pid] = sorted(
            facs.items(),
            key=lambda kv: (-kv[1], -faction_last_seen.get((pid, kv[0]), 0), kv[0]),
        )[0][0]

    return faction_map, games_played

@st.cache_data(ttl=600, show_spinner=False)
def league_rankings_rows() -> List[dict]:
    ensure_league_results_table()
    with Session(engine) as s:
        ratings = s.exec(select(LeagueRating).order_by(LeagueRating.rating.desc(), LeagueRating.player_name)).all()
        has_results = s.exec(select(LeagueResult)).first() is not None

    if has_results and not ratings:
        recalc_league_ratings()
        with Session(engine) as s:
            ratings = s.exec(select(LeagueRating).order_by(LeagueRating.rating.desc(), LeagueRating.player_name)).all()

    faction_map, games_played_map = _league_faction_and_games_maps()
    return [
        {
            "Rank": idx + 1,
            "ELO": round(r.rating),
            "Name": r.player_name,
            "Most Played Faction": faction_map.get(r.player_id, "—"),
            "Games Played": games_played_map.get(r.player_id, 0),
        }
        for idx, r in enumerate(ratings)
    ]

@st.cache_data(ttl=600, show_spinner=False)
def league_submitted_games_rows() -> List[dict]:
    ensure_league_results_table()
    with Session(engine) as s:
        league_results = s.exec(select(LeagueResult).order_by(LeagueResult.id)).all()

    return [
        {
            "Game Number": lr.id,
            "Player 1": lr.player_1_name,
            "P1 Faction": getattr(lr, "player_1_faction", None),
            "P1 Painting Bonus": getattr(lr, "player_1_painting_bonus", None),
            "P1 Painting Score": _league_painting_bonus_score(getattr(lr, "player_1_painting_bonus", None)),
            "Player 2": lr.player_2_name,
            "P2 Faction": getattr(lr, "player_2_faction", None),
            "P2 Painting Bonus": getattr(lr, "player_2_painting_bonus", None),
            "P2 Painting Score": _league_painting_bonus_score(getattr(lr, "player_2_painting_bonus", None)),
            "Result": lr.result,
            "Game Type": getattr(lr, "game_type", None) or "Competitive",
            "Date": lr.result_date,
            "P1 Before": round(lr.player_1_rating_before, 1) if lr.player_1_rating_before is not None else None,
            "P2 Before": round(lr.player_2_rating_before, 1) if lr.player_2_rating_before is not None else None,
            "P1 After": round(lr.player_1_rating_after, 1) if lr.player_1_rating_after is not None else None,
            "P2 After": round(lr.player_2_rating_after, 1) if lr.player_2_rating_after is not None else None,
            "K Used": lr.k_factor_used,
        }
        for lr in league_results
    ]

@st.cache_data(ttl=300, show_spinner=False)
def all_players_snapshot() -> List[dict]:
    with Session(engine) as s:
        players = s.exec(select(Player).order_by(Player.id)).all()
        return [
            {
                "id": p.id,
                "name": (p.name or "").strip(),
                "active": bool(p.active),
            }
            for p in players
            if p.id is not None and (p.name or "").strip()
        ]

@st.cache_data(ttl=300, show_spinner=False)
def active_players_snapshot() -> List[dict]:
    return [p for p in all_players_snapshot() if p.get("active", True)]

# ===================== Utilities / Theme =====================

_DEF_CSS = """
<style>
html, body, .stApp,
.stApp *, [class*="st-"], [data-testid] {
    font-family: 'Trebuchet MS', 'Lucida Sans Unicode', 'Lucida Grande', sans-serif !important;
}
/* Restore icon fonts so Material Symbols render as glyphs, not text */
[class*="material-icons"],
[class*="MaterialIcons"],
[class*="material-symbols"],
.stApp [class*="material-icons"] *,
.stApp [class*="material-symbols"] *,
span[data-testid="stIconMaterial"],
span[data-testid="stIconMaterial"] * {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
}
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


# ===================== Matchup Card Styling =====================

_MATCHUP_CSS = """
<style>
.matchup-card {
    background: linear-gradient(135deg, rgba(30,30,40,0.92) 0%, rgba(20,20,30,0.95) 100%);
    border: 1px solid rgba(180,150,90,0.35);
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
    color: #e8e4d8;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.matchup-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);
}
.matchup-grid {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 16px;
    align-items: center;
}
.matchup-side {
    text-align: center;
}
.matchup-side.left { text-align: right; }
.matchup-side.right { text-align: left; }
.matchup-name {
    font-size: 1.15rem;
    font-weight: 600;
    color: #f4e9c8;
    letter-spacing: 0.2px;
    margin-bottom: 4px;
}
.matchup-faction {
    font-size: 0.92rem;
    color: #b8a878;
    font-style: italic;
}
.matchup-vs {
    font-size: 1.5rem;
    font-weight: 800;
    color: #c9a14a;
    text-shadow: 0 0 8px rgba(201,161,74,0.4);
    letter-spacing: 1px;
    padding: 0 6px;
}
.matchup-meta {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px dashed rgba(180,150,90,0.25);
    display: flex;
    justify-content: center;
    gap: 22px;
    font-size: 0.88rem;
    color: #d4c8a0;
    flex-wrap: wrap;
}
.matchup-meta-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.matchup-meta-label {
    opacity: 0.7;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.6px;
}
.matchup-meta-value {
    font-weight: 600;
    color: #f0e4bc;
}
.matchup-bye .matchup-side.right .matchup-name {
    color: #8a8270;
    font-style: italic;
    font-weight: 400;
}
.matchup-tnt .matchup-vs {
    color: #d97a2a;
    text-shadow: 0 0 10px rgba(217,122,42,0.5);
}
.matchup-tnt-badge {
    display: inline-block;
    background: linear-gradient(135deg, #d97a2a, #b85a1a);
    color: #fff;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 3px 10px;
    border-radius: 12px;
    margin-bottom: 10px;
    box-shadow: 0 2px 6px rgba(217,122,42,0.35);
}
.matchup-accent-intro {
    border-color: rgba(110,180,110,0.7);
    box-shadow: 0 4px 14px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(110,180,110,0.25);
}
.matchup-accent-casual {
    border-color: rgba(201,161,74,0.75);
    box-shadow: 0 4px 14px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(201,161,74,0.3);
}
.matchup-accent-escalation {
    border-color: rgba(160,110,200,0.7);
    box-shadow: 0 4px 14px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(160,110,200,0.28);
}
.matchup-accent-competitive {
    border-color: rgba(210,80,80,0.75);
    box-shadow: 0 4px 14px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(210,80,80,0.3);
}
.matchup-accent-standard {
    border-color: rgba(201,161,74,0.75);
    box-shadow: 0 4px 14px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04), 0 0 0 1px rgba(201,161,74,0.3);
}

/* Stat strip — stays horizontal on mobile */
.stat-strip {
    display: flex;
    gap: 10px;
    margin: 4px 0 12px 0;
    width: 100%;
}
.stat-tile {
    flex: 1 1 0;
    min-width: 0;
    background: linear-gradient(135deg, rgba(30,30,40,0.92) 0%, rgba(20,20,30,0.95) 100%);
    border: 1px solid rgba(180,150,90,0.35);
    border-radius: 10px;
    padding: 10px 8px;
    text-align: center;
    box-shadow: 0 3px 10px rgba(0,0,0,0.3);
}
.stat-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #b8a878;
    margin-bottom: 4px;
}
.stat-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #f4e9c8;
    line-height: 1.1;
}
@media (max-width: 600px) {
    .stat-strip { gap: 6px; }
    .stat-tile { padding: 8px 4px; border-radius: 8px; }
    .stat-label { font-size: 0.6rem; letter-spacing: 0.4px; }
    .stat-value { font-size: 1.25rem; }
}

/* Tablet — slightly tighter layout */
@media (max-width: 768px) {
    .matchup-card {
        padding: 14px 14px;
        margin-bottom: 12px;
    }
    .matchup-grid { gap: 10px; }
    .matchup-name { font-size: 1.05rem; }
    .matchup-faction { font-size: 0.86rem; }
    .matchup-vs { font-size: 1.3rem; padding: 0 4px; }
}

/* Mobile — stack vertically, larger touch-friendly text */
@media (max-width: 600px) {
    .matchup-card {
        padding: 16px 14px;
        margin-bottom: 14px;
        border-radius: 14px;
    }
    .matchup-grid {
        grid-template-columns: 1fr;
        gap: 10px;
    }
    .matchup-side.left,
    .matchup-side.right {
        text-align: center;
    }
    .matchup-name {
        font-size: 1.18rem;
        margin-bottom: 2px;
    }
    .matchup-faction {
        font-size: 0.95rem;
        margin-bottom: 2px;
    }
    /* Replace inline VS with a slim divider for cleaner stacking */
    .matchup-vs {
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 3px;
        padding: 4px 0;
        position: relative;
        color: #c9a14a;
        text-shadow: 0 0 6px rgba(201,161,74,0.35);
        text-align: center;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .matchup-vs::before,
    .matchup-vs::after {
        content: "";
        display: inline-block;
        flex: 1;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(201,161,74,0.55), transparent);
        vertical-align: middle;
        margin: 0 10px;
    }
    .matchup-meta {
        gap: 10px 18px;
        margin-top: 12px;
        padding-top: 10px;
        font-size: 0.85rem;
        justify-content: space-around;
    }
    .matchup-meta-label {
        display: block;
        font-size: 0.65rem;
        margin-bottom: 1px;
    }
    .matchup-meta-item {
        flex-direction: column;
        gap: 0;
        align-items: center;
        text-align: center;
    }
    .matchup-tnt-badge {
        font-size: 0.65rem;
        padding: 3px 8px;
    }
}
</style>
"""


def render_matchup_card(player_a: str, faction_a: Optional[str], player_b: Optional[str],
                        faction_b: Optional[str], game_type: Optional[str],
                        eta: Optional[str], points: Optional[str], is_tnt: bool = False,
                        system: Optional[str] = None) -> str:
    """Build HTML for a single matchup card."""
    is_bye = not player_b or player_b.strip().startswith("—") or player_b == "BYE"
    classes = ["matchup-card"]
    if is_bye:
        classes.append("matchup-bye")
    if is_tnt:
        classes.append("matchup-tnt")

    # Border accent colour by game type — TOW and Horus Heresy only
    gt = (game_type or "").strip().lower()
    if system == "The Old World":
        if gt == "intro":
            classes.append("matchup-accent-intro")
        elif gt == "casual":
            classes.append("matchup-accent-casual")
        elif gt == "escalation":
            classes.append("matchup-accent-escalation")
        elif gt == "competitive":
            classes.append("matchup-accent-competitive")
    elif system == "The Horus Heresy":
        if gt == "intro":
            classes.append("matchup-accent-intro")
        elif gt == "standard":
            classes.append("matchup-accent-standard")

    tnt_badge = '<div style="text-align:center;"><span class="matchup-tnt-badge">⚔️ Triumph &amp; Treachery</span></div>' if is_tnt else ""

    fa = faction_a or "—"
    fb = faction_b if (player_b and not is_bye) else ""
    pb_display = player_b if (player_b and not is_bye) else "BYE / Standby"

    meta_items = []
    if game_type:
        meta_items.append(f'<span class="matchup-meta-item"><span class="matchup-meta-label">Type</span> <span class="matchup-meta-value">{game_type}</span></span>')
    if eta:
        meta_items.append(f'<span class="matchup-meta-item"><span class="matchup-meta-label">ETA</span> <span class="matchup-meta-value">{eta}</span></span>')
    if points:
        meta_items.append(f'<span class="matchup-meta-item"><span class="matchup-meta-label">Points</span> <span class="matchup-meta-value">{points}</span></span>')
    meta_html = f'<div class="matchup-meta">{"".join(meta_items)}</div>' if meta_items else ""

    return (
        f'<div class="{" ".join(classes)}">'
        f'{tnt_badge}'
        f'<div class="matchup-grid">'
        f'<div class="matchup-side left">'
        f'<div class="matchup-name">{player_a}</div>'
        f'<div class="matchup-faction">{fa}</div>'
        f'</div>'
        f'<div class="matchup-vs">VS</div>'
        f'<div class="matchup-side right">'
        f'<div class="matchup-name">{pb_display}</div>'
        f'<div class="matchup-faction">{fb}</div>'
        f'</div>'
        f'</div>'
        f'{meta_html}'
        f'</div>'
    )


def render_stat_strip(stats: list) -> str:
    """Build a horizontal stat strip that stays side-by-side on mobile.
    `stats` is a list of (label, value) tuples."""
    tiles = "".join(
        f'<div class="stat-tile"><div class="stat-label">{label}</div>'
        f'<div class="stat-value">{value}</div></div>'
        for label, value in stats
    )
    return f'<div class="stat-strip">{tiles}</div>'


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
    # Build triple images from secrets or local files; if none found, fall back to existing single-logo logic.
    # TOW candidates include Old World files; HH includes heresy keywords; KT includes kill team keywords.
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
        'The Horus Heresy'
    )
    kt_img = _img_html_from_secret_or_file(
        LOGO_KT_URL,
        ['killteam.png','killteam.jpg','kill_team.png','kill_team.jpg','kt_logo.png','kt_logo.jpg'],
        HEADER_LOGO_WIDTH,
        'Kill Team'
    )

    # Fallback to previous single-logo pipeline if none produced output
    if not (tow_img or hh_img or kt_img):
        logo_html = ""
        if LOGO_URL:
            logo_html = f"<img src='{LOGO_URL}' alt='Logo' width='{LOGO_WIDTH}'/>"
        else:
            lp = _find_logo_path()
            if lp:
                with open(lp, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode()
                ext = lp.lower().split(".")[-1]
                mime = "image/png" if ext == "png" else "image/jpeg"
                logo_html = f"<img src='data:{mime};base64,{encoded}' alt='Logo' width='{LOGO_WIDTH}'/>"
        header_html = f"<div class='owl-logos'>{logo_html}</div>"
    else:
        imgs = "".join(img for img in [tow_img, hh_img, kt_img] if img)
        header_html = f"<div class='owl-logos'>{imgs}</div>"

    st.markdown(f"""
<style>
.owl-logos {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 24px;
    width: 100%;
}}
.owl-logos img {{
    max-width: 100%;
    height: auto;
    flex: 0 0 auto;
}}
@media (max-width: 768px) {{
    .owl-logos {{ gap: 14px; }}
    .owl-logos img {{ width: calc((100% - 28px) / 3) !important; min-width: 90px; }}
}}
@media (max-width: 480px) {{
    .owl-logos {{ gap: 10px; }}
    .owl-logos img {{ width: calc((100% - 20px) / 3) !important; min-width: 70px; }}
}}
.owl-title {{
    margin: 0 !important;
    padding: 0 !important;
    text-align: center;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
}}
@media (max-width: 600px) {{
    .owl-title {{
        font-size: 1.6rem !important;
        letter-spacing: 1px;
    }}
}}
</style>
<div class='owl-header' style='display:flex;flex-direction:column;align-items:center;gap:.35rem;margin:1.0rem 0 .6rem;width:100%;'>
  {header_html}
  <h1 class='owl-title'>CALL TO ARMS</h1>
</div>
<div class='owl-spacer'></div>
""", unsafe_allow_html=True)


def _get_tow_signup_count(week_str: str) -> int:
    """Return number of TOW signups for the given week id."""
    try:
        wk = (week_str or "").strip()
    except Exception:
        wk = week_str
    if not wk:
        return 0
    with Session(engine) as s:
        rows = s.exec(
            select(Signup).where(
                (Signup.week == wk) & (Signup.system == "The Old World")
            )
        ).all()
        return len(rows)


def post_discord_signup(player_name: str, faction: Optional[str], vibe: Optional[str], system: str, week_str: str):
    """Post a minimal signup notification to Discord via webhook (TOW only)."""
    if system != "The Old World":
        return
    if not DISCORD_SIGNUP_WEBHOOK_URL:
        return

    faction_label = faction or "Unknown faction"
    vibe_label = vibe or "Unknown vibe"
    count = _get_tow_signup_count(week_str)

    content = f"📝 **{player_name}** signed up — ⚔️ {faction_label} • 🎭 {vibe_label}\n📊 TOW signups this week: {count}"

    try:
        requests.post(
            DISCORD_SIGNUP_WEBHOOK_URL,
            json={"content": content},
            timeout=5,
        )
    except Exception:
        # Do not break the app if Discord is unreachable
        pass


def post_discord_drop(player_name: str, faction: Optional[str], vibe: Optional[str], week_str: str):
    """Post a minimal drop notification to Discord via webhook (TOW only)."""
    if not DISCORD_SIGNUP_WEBHOOK_URL:
        return
    # We don't know system here for sure, but drops are only enabled for TOW signups usage-wise.
    count = _get_tow_signup_count(week_str)

    faction_label = faction or "Unknown faction"
    vibe_label = vibe or "Unknown vibe"

    content = f"❌ **{player_name}** dropped — ⚔️ {faction_label} • 🎭 {vibe_label}\n📊 TOW signups this week: {count}"
    try:
        requests.post(
            DISCORD_SIGNUP_WEBHOOK_URL,
            json={"content": content},
            timeout=5,
        )
    except Exception:
        pass






def render_pairings_ascii_table(rows: list[dict], week: str, system: str) -> str:
    """
    Render the public-style pairings rows into an ASCII table suitable for Discord.
    Expects rows with keys: A, Faction A, B, Faction B, Type, ETA, Points.
    """
    if not rows:
        return f"No pairings for {system} — {week}."

    header = ["#", "A", "Faction A", "B", "Faction B", "Type", "ETA", "Pts"]
    body = []
    for i, r in enumerate(rows, start=1):
        body.append([
            i,
            r.get("A", "") or "",
            r.get("Faction A", "") or "",
            r.get("B", "") or "",
            r.get("Faction B", "") or "",
            r.get("Type", "") or "",
            r.get("ETA", "") or "",
            r.get("Points", "") or "",
        ])

    table = t2a(
        header=header,
        body=body,
        style=PresetStyle.thin_compact,
    )

    title = f"**{system} Pairings — {week}**"
    return f"{title}\n```text\n{table}\n```"



def render_pairings_image(rows: list[dict], week: str, system: str) -> io.BytesIO | None:
    """Render pairings as a PNG image using matplotlib, for Discord posting.

    Returns a BytesIO buffer positioned at start, or None if rows is empty.
    """
    if not rows:
        return None

    # Build a simple DataFrame with a numeric index column
    df = pd.DataFrame(rows)
    cols = ["A", "Faction A", "B", "Faction B", "Type", "ETA", "Points"]
    df = df[cols]
    df.insert(0, "#", range(1, len(df) + 1))

    # --- sizing: large text, minimal padding ---
    n_rows = len(df)
    height = max(4.0, 0.7 * n_rows + 2)

    bg_color = "#0E1117"
    header_bg = "#1E2634"
    text_color = "#FFFFFF"
    edge_color = "#FFFFFF"

    fig, ax = plt.subplots(figsize=(16, height))
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    ax.axis("off")

    table = ax.table(
        cellText=df.values.tolist(),
        colLabels=df.columns.tolist(),
        loc="center",
        cellLoc="left",
        bbox=[0, 0, 1, 1],
    )

    table.auto_set_font_size(False)
    # Bigger font, but cells not overly inflated
    table.set_fontsize(20)
    table.scale(1.2, 1.4)

    try:
        table.auto_set_column_width(col=list(range(len(df.columns))))
    except Exception:
        pass

    for (row, col), cell in table.get_celld().items():
        # Reduce inner padding inside each cell so text hugs the borders more
        try:
            cell.PAD = 0.02
        except Exception:
            pass
        cell.set_edgecolor(edge_color)
        cell.set_text_props(color=text_color, ha="left", va="center")
        if row == 0:
            cell.set_facecolor(header_bg)
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor(bg_color)

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=150,
        bbox_inches="tight",
        pad_inches=0,
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    buf.seek(0)
    return buf



def post_pairings_table_to_discord(rows: list[dict], week: str, system: str) -> None:
    """
    Post the public pairings table to Discord via the pairings webhook.
    Uses an image of the table when possible, with a text title, and falls back to ASCII.
    Does nothing if no webhook is configured.
    """
    if not DISCORD_PAIRINGS_WEBHOOK_URL:
        return

    title = f"**{system} Pairings — {week}**"

    img_buf = None
    try:
        img_buf = render_pairings_image(rows, week, system)
    except Exception:
        img_buf = None

    try:
        if img_buf is not None:
            files = {"file": ("pairings.png", img_buf, "image/png")}
            payload = {"content": title}
            requests.post(
                DISCORD_PAIRINGS_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files,
                timeout=10,
            )
        else:
            content = render_pairings_ascii_table(rows, week, system)
            requests.post(
                DISCORD_PAIRINGS_WEBHOOK_URL,
                json={"content": content},
                timeout=10,
            )
    except Exception:
        # Do not break the app if Discord is unreachable
        pass


CALL_TO_ARMS_TEMPLATE = """📣 I SUMMON THE ELECTOR COUNTS 📣

🎲 Scenario of the week: {scenario_name}

- Common Objectives:
{common_objectives}

- Secondary Objectives:
{secondary_objectives}

⚔️ Army Composition Rules: Combined Arms and Grand Melee, Square Based Comp (optional if pre-agreed for competitive matches only) 

Complete the online form if you are coming this Wednesday {wednesday_date}. The recommended start is 18:00-19:00. 

➡️ https://calltoarms.streamlit.app/

🤖 Your new AI overlords will pair everybody up based on responses and will make a post on Tuesday evening. If you wish to pre-arrange a game, feel free and just let us know so we can anticipate the numbers.
"""


def pick_random_tow_scenario() -> dict | None:
    """Return a random TOW scenario from the pool, or None if empty."""
    if not TOW_SCENARIOS:
        return None
    return random.choice(TOW_SCENARIOS)


def next_wednesday(from_date: date | None = None) -> date:
    """Return the upcoming Wednesday date, assuming games are on Wednesdays."""
    if from_date is None:
        from_date = date.today()
    # 0=Mon,1=Tue,2=Wed,...
    days_ahead = (2 - from_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # Always pick the *next* Wednesday, not today
    return from_date + timedelta(days=days_ahead)


def build_tow_call_to_arms_message(scenario: dict, wednesday_date: date) -> str:
    """Fill in the Call to Arms template with scenario + date."""
    weds_str = wednesday_date.strftime("%d/%m/%Y")  # e.g. 26/11/2025
    return CALL_TO_ARMS_TEMPLATE.format(
        scenario_name=scenario.get("name", "Unknown Scenario"),
        common_objectives=COMMON_OBJECTIVES_TOW,
        secondary_objectives=scenario.get("secondary_objectives", ""),
        wednesday_date=weds_str,
    )


def post_tow_call_to_arms_with_image(scenario: dict, wednesday_date: date | None = None) -> None:
    """
    Post the weekly TOW Call to Arms message to Discord via the call-to-arms webhook.
    If a terrain image exists on disk for this scenario, it will be uploaded with the message.
    """
    if not DISCORD_CALL_TO_ARMS_WEBHOOK_URL:
        return  # nothing configured

    if wednesday_date is None:
        wednesday_date = next_wednesday()

    content = build_tow_call_to_arms_message(scenario, wednesday_date)
    payload = {"content": content}

    terrain_path = scenario.get("terrain_path")
    if terrain_path:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            full_path = os.path.join(base_dir, terrain_path)
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    files = {"file": (os.path.basename(full_path), f, "image/png")}
                    requests.post(
                        DISCORD_CALL_TO_ARMS_WEBHOOK_URL,
                        data={"payload_json": json.dumps(payload)},
                        files=files,
                        timeout=10,
                    )
                    return
        except Exception:
            # Fall back to plain text post if file upload fails
            pass

    try:
        requests.post(
            DISCORD_CALL_TO_ARMS_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
    except Exception:
        # Do not break callers if Discord is unreachable
        pass




def run_scheduled_tow_call_to_arms() -> None:
    """Entry point for GitHub Actions to post the weekly TOW Call to Arms.

    This helper is intentionally Streamlit-agnostic so it can be imported and run
    from bare Python (e.g. `python run_call_to_arms.py`) without requiring a
    Streamlit runtime or secrets.toml. It relies on DISCORD_CALL_TO_ARMS_WEBHOOK_URL
    being provided either via Streamlit secrets or environment variables.
    """
    # Pick a random scenario from the configured pool
    scenario = pick_random_tow_scenario()
    if not scenario:
        # Nothing to post if there are no scenarios configured
        return

    # Use the default upcoming Wednesday
    post_tow_call_to_arms_with_image(scenario)
def _parse_eta(sval) -> Optional[time]:
    """Parse an HH:MM string to a time object, returning None on failure."""
    if not sval:
        return None
    try:
        return datetime.strptime(str(sval).strip(), "%H:%M").time()
    except Exception:
        return None


def _eta_show_for_pair(a_su, b_su) -> Optional[str]:
    """Return the later ETA of two signups as 'HH:MM', or None if both are absent."""
    ta = _parse_eta(a_su.eta if a_su else None)
    tb = _parse_eta(b_su.eta if b_su else None)
    if ta and tb:
        return max(ta, tb).strftime("%H:%M")
    if ta:
        return ta.strftime("%H:%M")
    if tb:
        return tb.strftime("%H:%M")
    return None


def _pts_show_for_pair(a_su, b_su) -> Optional[int]:
    """Return the lower points value of two signups, or None if neither has points."""
    vals = [
        su.points for su in (a_su, b_su)
        if su is not None and isinstance(su.points, int)
    ]
    return min(vals) if vals else None


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



def week_id_fri(d: date) -> str:
    """Friday identifier (DD/MM/YYYY) for Horus Heresy and Kill Team."""
    # 0 = Mon, 1 = Tue, ..., 4 = Fri
    days_ahead = (4 - d.weekday()) % 7
    friday = d + timedelta(days=days_ahead)
    return uk_date_str(friday)

def week_id_for_system(system: str, d: date | None = None) -> str:
    """Per-system game-day week id: TOW uses Wednesday, HH and Kill Team use Friday."""
    if d is None:
        d = date.today()
    if system in ("The Horus Heresy", "Kill Team"):
        return week_id_fri(d)
    # Default to TOW behaviour
    return week_id_wed(d)

def parse_week_id(week_str: str) -> date:
    """Parse a week identifier like 'DD/MM/YYYY' into a date."""
    return datetime.strptime(week_str.strip(), "%d/%m/%Y").date()


# ---- Cache helpers ----
@st.cache_data(ttl=300)
def player_name_map() -> Dict[int, str]:
    with Session(engine) as s:
        return {p.id: p.name for p in s.exec(select(Player)).all()}

# ===================== Pairing Logic =====================

def _normalize_name(n: str) -> str:
    return " ".join(n.strip().split())

@st.cache_data(ttl=300)
def previous_pairs_recent(system: str, current_week: str, max_weeks: int = 2) -> Set[Tuple[str, str]]:
    """Return unordered player pairs who have played each other within the last `max_weeks` weeks for this system."""
    try:
        current_dt = parse_week_id(current_week)
    except Exception:
        return set()

    with Session(engine) as s:
        # Load all pairings for the system in one query, then filter in Python
        prs = s.exec(select(Pairing).where(Pairing.system == system)).all()

        # Keep only recent paired (non-BYE) pairings — filter before touching Signup table
        recent_prs = []
        for pr in prs:
            if pr.b_signup_id is None:
                continue
            try:
                pr_week_dt = parse_week_id(pr.week)
            except Exception:
                continue
            if abs((current_dt - pr_week_dt).days) // 7 <= max_weeks:
                recent_prs.append(pr)

        if not recent_prs:
            return set()

        # Batch-fetch all relevant Signup rows in one query (fixes N+1)
        signup_ids = {pr.a_signup_id for pr in recent_prs} | {pr.b_signup_id for pr in recent_prs}
        signup_by_id = {
            su.id: su
            for su in s.exec(select(Signup).where(Signup.id.in_(signup_ids))).all()
        }

        out: Set[Tuple[str, str]] = set()
        for pr in recent_prs:
            a = signup_by_id.get(pr.a_signup_id)
            b = signup_by_id.get(pr.b_signup_id)
            if not a or not b:
                continue
            na = _normalize_name(a.player_name).lower()
            nb = _normalize_name(b.player_name).lower()
            if na == nb:
                continue
            out.add(tuple(sorted([na, nb])))
        return out



@dataclass
class MatcherSignup:
    row: Signup
    key: str  # normalized unique key (player name)
    preference: Tuple[int,int,int]  # heuristic tuple for matching

def build_match_preference(su: Signup) -> Tuple[int,int,int]:
    v = (su.vibe or "").strip().lower()
    vibe_w = 0 if (v.startswith("casual") or v == "escalation") else 1
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
        if system in ("The Old World","The Horus Heresy"):  # Kill Team has no intro/demo mechanic
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
                    s.add(p); s.flush()
                    intro_pairs.append(p)
                    used_intro.add(seeker.key); used_intro.add(best.key)
            candidates = [m for m in candidates if m.key not in used_intro]

        candidates.sort(key=lambda m: ((0 if ((m.row.vibe or "").strip().lower() == "escalation") else 1) if system == "The Old World" else 0, m.preference, m.key))
        # If T&T grouping is enabled and we have an odd number of candidates,
        # and at least three players have opted into Triumph & Treachery, bias
        # the eventual BYE towards a T&T-capable player. This keeps the odd
        # player as someone who is happy to be folded into a 3-way game.
        if allow_tnt and system == "The Old World" and (len(candidates) % 2 == 1):
            tnt_pool = [m for m in candidates if getattr(m.row, "tnt_ok", False)]
            if len(tnt_pool) >= 3:
                # Move one T&T player to the end of the list so the standard
                # greedy matcher naturally leaves them unmatched if a BYE is
                # required.
                chosen = tnt_pool[-1]
                candidates = [m for m in candidates if m.key != chosen.key] + [chosen]


        seen_pairs = previous_pairs_recent(system, week, max_weeks=2)
        used: Set[str] = set()
        out: List[Pairing] = intro_pairs

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
            if system_name != "The Old World":
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

        def _escalation_priority_penalty(a_row, b_row, system_name):
            """Bias TOW 'Escalation' players to match each other first, else prefer Casual/Either."""
            if system_name != "The Old World":
                return 0
            av = ((getattr(a_row, "vibe", None) or "").strip().lower())
            bv = ((getattr(b_row, "vibe", None) or "").strip().lower())
            if av != "escalation":
                return 0
            if bv == "escalation":
                return 0
            if bv in ("casual", "either"):
                return 1
            return 2

        def _pair_dist(ms, other):
            """Compute the lexicographic distance tuple used for greedy matching."""
            dv_base = abs(ms.preference[0] - other.preference[0])
            dv = _vibe_distance_override(ms.row, other.row, dv_base)
            de = abs(ms.preference[1] - other.preference[1])
            # Kill Team has no army points: zero the points bucket distance
            dp = 0 if system == "Kill Team" else abs(ms.preference[2] - other.preference[2])
            eta_b = _eta_bucket_diff(ms.row, other.row)
            scen_d = _scenario_diff_tow(ms.row, other.row, system)
            mir = _mirror_flag(ms.row, other.row)
            esc_p = _escalation_priority_penalty(ms.row, other.row, system)
            return (esc_p, mir, eta_b, scen_d, dv, de, dp)

        for i, ms in enumerate(candidates):
            if ms.key in used:
                continue
            # Find best candidate not used, minimal "distance"
            best_j = None
            best_dist = (99, 99, 99, 99, 99, 99, 99)
            for j in range(i+1, len(candidates)):
                other = candidates[j]
                if other.key in used or has_played(ms.key, other.key):
                    continue
                dist = _pair_dist(ms, other)
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
                    if dist == (0, 0, 0, 0, 0, 0, 0):
                        break
            # If no non-rematch found, allow a rematch if permitted
            if best_j is None and allow_repeats_when_needed:
                for j in range(i+1, len(candidates)):
                    other = candidates[j]
                    if other.key in used:
                        continue
                    dist = _pair_dist(ms, other)
                    if dist < best_dist:
                        best_dist = dist
                        best_j = j
                        if dist == (0, 0, 0, 0, 0, 0, 0):
                            break
            if best_j is None:
                # leave as BYE / potential T&T grouping
                p = Pairing(
                    week=week, system=system,
                    a_signup_id=ms.row.id, b_signup_id=None,
                    status="pending",
                    a_faction=ms.row.faction, b_faction=None
                )
                s.add(p); s.flush(); out.append(p)
                used.add(ms.key)
            else:
                other = candidates[best_j]
                p = Pairing(
                    week=week, system=system,
                    a_signup_id=ms.row.id, b_signup_id=other.row.id,
                    status="pending",
                    a_faction=ms.row.faction, b_faction=other.row.faction
                )
                s.add(p); s.flush(); out.append(p)
                used.add(ms.key); used.add(other.key)

        s.commit()
        return out

# ===================== UI =====================

apply_theme()
st.markdown(_MATCHUP_CSS, unsafe_allow_html=True)
render_header()

# ---- Sidebar: Access & quick links ----
with st.sidebar:
    st.header("Access")
    if not st.session_state.is_admin:
        with st.form("admin_unlock_form"):
            pw = st.text_input("Admin Password", type="password")
            submitted = st.form_submit_button("Unlock Admin", width='stretch')
        if submitted:
            if pw == ADMIN_PASSWORD:
                st.session_state.is_admin = True
                st.success("Admin mode unlocked."); st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        st.success("Admin mode active")
        if st.button("Lock", width='stretch'):
            st.session_state.is_admin = False
            st.rerun()
        # DB download if SQLite
        if not DATABASE_URL and os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "rb") as f:
                    data = f.read()
                st.download_button("Download DB", data=data, file_name=DB_PATH, mime="application/octet-stream", width='stretch')
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

tabs_public = ["Call to Arms", "Pairings", "Old World League"]
tabs_admin  = ["Signups", "Pairings Admin", "League", "View History"]
order = tabs_public + (tabs_admin if st.session_state.get("is_admin") else [])
T = st.tabs(order)
idx = {name:i for i,name in enumerate(order)}

# --------------- Public: Call to Arms ---------------
with T[idx["Call to Arms"]]:
    st.subheader("Join This Week's Games")

    c1, c2 = st.columns([1,2])
    with c1:
        system = st.selectbox("System", SYSTEMS, index=0)

    with c2:
        week_default = week_id_for_system(system, date.today())
        week_val = st.text_input(
            "Week (DD/MM/YYYY)",
            value=week_default,
            key=f"cta_week_{system}",
            help="The Old World uses Wednesday; The Horus Heresy and Kill Team use Friday as the week id."
        )

    # --- Live signup snapshot for this week/system ---
    try:
        with Session(engine) as _s_cnt:
            _wk_sus = _s_cnt.exec(
                select(Signup).where((Signup.week == week_val) & (Signup.system == system))
            ).all()
        # Latest signup per unique normalised player name
        _latest_by_name = {}
        for _su in _wk_sus:
            _k = _normalize_name(_su.player_name or "").lower()
            _prev = _latest_by_name.get(_k)
            if (not _prev) or (_su.created_at > _prev.created_at):
                _latest_by_name[_k] = _su
        _unique_signups = list(_latest_by_name.values())
        _new_count = sum(1 for s in _unique_signups if (s.experience or "").lower() == "new")
        _vet_count = sum(1 for s in _unique_signups if (s.experience or "").lower() == "veteran")

        mc_html = render_stat_strip([
            ("Signed Up", len(_unique_signups)),
            ("Newcomers", _new_count),
            ("Veterans", _vet_count),
        ])
        st.markdown(mc_html, unsafe_allow_html=True)
    except Exception:
        pass

    st.divider()
    # --- Player pick or create (first+last only) ---
    with Session(engine) as _s_pl:
        _players_all = _s_pl.exec(select(Player).order_by(Player.id)).all()

    def _fmt_player_label(p):
        nm = (getattr(p, "name", "") or "").strip()
        return f"#{p.id} — {nm or 'Unnamed'}"

    _player_labels = [_fmt_player_label(p) for p in _players_all]
    _label_to_id = { _fmt_player_label(p): p.id for p in _players_all }

    st.markdown("### Who Are You?")
    _is_new = st.checkbox("I'm New (Create a Player Profile)")

    selected_player_label = None
    first = ""
    last = ""

    is_hh = (system == "The Horus Heresy")
    is_kt = (system == "Kill Team")

    if not _is_new:
        selected_player_label = st.selectbox(
            "Select Your Player",
            options=(['— Select —'] + _player_labels),
            index=0,
            placeholder="Type to search…"
        )
    else:
        _cfa, _cfb = st.columns(2)
        with _cfa:
            first = st.text_input("First Name *")
        with _cfb:
            last = st.text_input("Last Name *")

    # Look up this player's most recent signup to prefill fields
    last_su = None
    if not _is_new and selected_player_label and selected_player_label in _label_to_id:
        with Session(engine) as _s_pref:
            _pid = _label_to_id[selected_player_label]
            last_su = _s_pref.exec(
                select(Signup)
                .where(
                    (Signup.player_id == _pid) & (Signup.system == system)
                )
                .order_by(Signup.id.desc())
            ).first()

    # Defaults (fallback to current behaviour if no previous signup)
    default_faction = None
    default_pts = 3000 if is_hh else 2000
    default_eta = "18:30"
    default_exp = "New"
    default_vibe = "Standard" if is_hh else "Casual"
    default_standby = False
    default_tnt = False
    default_scenario = "Open Battle" if not is_hh else None
    default_can_demo = False

    if last_su:
        if last_su.faction:
            default_faction = last_su.faction
        if last_su.points is not None:
            default_pts = last_su.points
        if last_su.eta:
            default_eta = last_su.eta
        if last_su.experience:
            default_exp = last_su.experience
        if last_su.vibe:
            default_vibe = last_su.vibe
        default_standby = bool(last_su.standby_ok)
        default_tnt = bool(last_su.tnt_ok)
        if last_su.scenario and not is_hh:
            default_scenario = last_su.scenario
        default_can_demo = bool(last_su.can_demo)

    if not _is_new and selected_player_label and selected_player_label in _label_to_id:
        _key_suffix = str(_label_to_id[selected_player_label])
    else:
        _key_suffix = "new"

    with st.form("signup_form", clear_on_submit=True):
        # Factions
        if is_hh:
            faction_options = HH_FACTIONS_WITH_BLANK
        elif is_kt:
            faction_options = KT_FACTIONS_WITH_BLANK
        else:
            faction_options = PLACEHOLDER_FACTIONS_WITH_BLANK

        faction_index = 0
        if default_faction and default_faction in faction_options:
            faction_index = faction_options.index(default_faction)

        faction_label = "Your Kill Team" if is_kt else "Your Faction"
        faction_choice = st.selectbox(faction_label, faction_options, index=faction_index, key=f"signup_faction_{system}_{_key_suffix}")
        # Points (not shown for Kill Team)
        if not is_kt:
            pts = st.number_input("Army Points", min_value=0, max_value=10000, value=int(default_pts), step=50, key=f"signup_pts_{system}_{_key_suffix}")
            if not is_hh:
                st.caption("If selecting an Escalation game, please input backup army points limit.")
        else:
            pts = 0
        # ETA dropdown 17:00-19:30
        eta_options = []
        for h in [17,18,19]:
            for m in [0,15,30,45]:
                if h == 19 and m > 30:
                    continue
                eta_options.append(f"{h:02d}:{m:02d}")
        eta_label = default_eta if default_eta in eta_options else "18:30"
        eta_default_idx = eta_options.index(eta_label) if eta_label in eta_options else 0
        eta = st.selectbox("Estimated Time of Arrival", eta_options, index=eta_default_idx, key=f"signup_eta_{system}_{_key_suffix}")
        exp_options = ["New", "Some", "Veteran"]
        exp_index = exp_options.index(default_exp) if default_exp in exp_options else 0
        exp = st.selectbox("Experience", exp_options, index=exp_index, key=f"signup_exp_{system}_{_key_suffix}")
        # Type of game (not shown for Kill Team)
        if is_hh:
            vibe_options = ["Standard", "Intro"]
            vibe_index = vibe_options.index(default_vibe) if default_vibe in vibe_options else 0
            vibe = st.selectbox("Type of Game", vibe_options, index=vibe_index, key=f"signup_vibe_{system}_{_key_suffix}")
        elif is_kt:
            vibe = "Standard"
        else:
            vibe_options = ["Casual", "Competitive", "Escalation", "Intro", "Either"]
            vibe_index = vibe_options.index(default_vibe) if default_vibe in vibe_options else 0
            vibe = st.selectbox("Type of Game", vibe_options, index=vibe_index, key=f"signup_vibe_{system}_{_key_suffix}")
        standby = st.checkbox("I Can Be on Standby", value=default_standby, key=f"signup_standby_{system}_{_key_suffix}")
        # Triumph & Treachery (TOW only)
        if not is_hh and not is_kt:
            tnt = st.checkbox("I Can Play Triumph & Treachery (3-Way)", value=default_tnt, key=f"signup_tnt_{system}_{_key_suffix}")
        else:
            tnt = False
        # Scenario (TOW only)
        if not is_hh and not is_kt:
            scen_options = ["Open Battle", "Weekly Scenario"]
            scen_index = scen_options.index(default_scenario) if default_scenario in scen_options else 0
            scenario = st.selectbox("Scenario Preference", scen_options, index=scen_index, key=f"signup_scenario_{system}_{_key_suffix}")
        else:
            scenario = None
        # Intro game leadership (not shown for Kill Team)
        if not is_kt:
            can_demo = st.checkbox("I Can Lead an Intro Game", value=default_can_demo, key=f"signup_demo_{system}_{_key_suffix}")
        else:
            can_demo = False

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
            week_clean = week_val.strip()

            # Prevent accidental duplicate signups for the same player/week/system.
            # If the player already has a signup, update the latest row instead
            # of inserting a second row; remove older duplicates for this same key.
            existing_signups = s.exec(
                select(Signup)
                .where(
                    (Signup.week == week_clean)
                    & (Signup.system == system)
                    & (Signup.player_id == pl.id)
                )
                .order_by(Signup.id.desc())
            ).all()

            created_new_signup = not bool(existing_signups)
            if existing_signups:
                su = existing_signups[0]
                for duplicate_su in existing_signups[1:]:
                    s.delete(duplicate_su)
                su.player_name = pl.name
                su.faction = faction
                su.points = int(pts)
                su.eta = eta.strip() or None
                su.experience = exp
                su.vibe = vibe
                su.standby_ok = standby
                su.tnt_ok = tnt
                su.scenario = scenario
                su.can_demo = can_demo
                s.add(su)
            else:
                su = Signup(
                    week=week_clean, system=system,
                    player_id=pl.id, player_name=pl.name,
                    faction=faction, points=int(pts), eta=eta.strip() or None,
                    experience=exp, vibe=vibe,
                    standby_ok=standby, tnt_ok=tnt,
                    scenario=scenario, can_demo=can_demo
                )
                s.add(su)

            s.commit()
            invalidate_app_caches()

            player_name_for_webhook = pl.name

        # Discord notification for TOW signups: only send for a brand-new signup,
        # not for an accidental double-click/update of an existing row.
        if created_new_signup:
            post_discord_signup(player_name_for_webhook, faction, vibe, system, week_val.strip())
            st.success("Thanks! You're on the list.")
        else:
            st.success("Your existing signup for this week has been updated.")

    st.markdown("### Need to Drop Out?")
    if not _is_new and selected_player_label and selected_player_label in _label_to_id:
        if st.button("Drop My Signup for This Week"):
            with Session(engine) as s:
                # Block drops after pairings have been published for this week/system
                gate = s.exec(
                    select(PublishState).where(
                        (PublishState.week == week_val.strip())
                        & (PublishState.system == system)
                    )
                ).first()
                if gate and gate.published:
                    st.warning("Pairings have been published - Contact the session organiser if you need to drop out.")
                    st.stop()

                pid = _label_to_id[selected_player_label]
                su_rows = s.exec(
                    select(Signup).where(
                        (Signup.week == week_val.strip())
                        & (Signup.system == system)
                        & (Signup.player_id == pid)
                    )
                ).all()
                if not su_rows:
                    st.info("No signup found for you this week to drop.")
                else:
                    # Use the first matching signup row to get player name/faction/vibe before deleting
                    ref = su_rows[0]
                    for su in su_rows:
                        s.delete(su)
                    s.commit()
                    invalidate_app_caches()
                    st.success("You've been removed from this week's signup.")
                    # Discord notification for TOW drops
                    if system == "The Old World":
                        post_discord_drop(ref.player_name, ref.faction, ref.vibe, week_val.strip())
    else:
        st.caption("Select your player above to drop an existing signup.")


# --------------- Public: Pairings view ---------------
with T[idx["Pairings"]]:
    st.subheader("Weekly Pairings")

    sys_pick = st.selectbox("System", SYSTEMS, index=0, key="pub_sys")

    week_lookup = st.text_input(
        "Week (DD/MM/YYYY)",
        value=week_id_for_system(sys_pick, date.today()),
        key=f"pub_week_{sys_pick}",
        help="The Old World uses the Wednesday date; The Horus Heresy and Kill Team use the Friday date."
    )

    # Fetch PublishState, Pairings, and Signups in a single session
    with Session(engine) as s:
        gate = s.exec(
            select(PublishState).where(
                (PublishState.week == week_lookup) & (PublishState.system == sys_pick)
            )
        ).first()
        if gate and gate.published:
            prs = s.exec(
                select(Pairing)
                .where((Pairing.week == week_lookup) & (Pairing.system == sys_pick))
                .order_by(Pairing.id)
            ).all()
            if prs:
                signup_ids = {p.a_signup_id for p in prs} | {p.b_signup_id for p in prs if p.b_signup_id}
                signup_by_id = {
                    su.id: su
                    for su in s.exec(select(Signup).where(Signup.id.in_(signup_ids))).all()
                } if signup_ids else {}
            else:
                signup_by_id = {}
        else:
            prs = []
            signup_by_id = {}

    if not gate or not gate.published:
        st.info("No pairings published yet for this week/system.")
    elif not prs:
        st.info("No pairings yet.")
    else:
        tnt_names = set(TNT_SUGGESTIONS.get((week_lookup, sys_pick), []))

        # Summary metrics
        total_games = len([p for p in prs if p.b_signup_id is not None])
        total_players = len({p.a_signup_id for p in prs} | {p.b_signup_id for p in prs if p.b_signup_id})
        bye_count = len([p for p in prs if p.b_signup_id is None])

        st.markdown(render_stat_strip([
            ("Players", total_players),
            ("Matchups", total_games),
            ("On Standby", bye_count),
        ]), unsafe_allow_html=True)

        for p in prs:
            a = signup_by_id.get(p.a_signup_id)
            b = signup_by_id.get(p.b_signup_id) if p.b_signup_id else None

            eta_show = _eta_show_for_pair(a, b)
            pts_show = _pts_show_for_pair(a, b)

            type_pub = _public_vibe_display(getattr(a, "vibe", None), getattr(b, "vibe", None))
            is_tnt = False
            if sys_pick == "The Old World" and tnt_names:
                if (a and a.player_name in tnt_names) or (b and b.player_name in tnt_names):
                    type_pub = "T&T"
                    is_tnt = True

            st.markdown(render_matchup_card(
                player_a=a.player_name if a else f"A#{p.a_signup_id}",
                faction_a=p.a_faction or (a.faction if a else None),
                player_b=(b.player_name if b else None),
                faction_b=(p.b_faction or (b.faction if b else None) if b else None),
                game_type=type_pub,
                eta=eta_show,
                points=pts_show,
                is_tnt=is_tnt,
                system=sys_pick,
            ), unsafe_allow_html=True)

# --------------- Public: Old World League ---------------
with T[idx["Old World League"]]:
    st.markdown("### League Rankings")
    league_rows = league_rankings_rows()
    if league_rows:
        st.dataframe(league_rows, width='stretch', hide_index=True)
    else:
        empty_league = pd.DataFrame(columns=["Rank", "ELO", "Name", "Most Played Faction", "Games Played"])
        st.dataframe(empty_league, width='stretch', hide_index=True)
        st.info("League rankings will appear here once league results have been submitted.")

    st.divider()
    st.markdown("### Results Submission")
    result_players = sorted(active_players_snapshot(), key=lambda p: p["name"].lower())

    player_label_options = ["— None —", *[f"#{p['id']} — {p['name']}" for p in result_players]]
    player_label_to_id = {f"#{p['id']} — {p['name']}": p["id"] for p in result_players}
    player_id_to_name = {p["id"]: p["name"] for p in result_players}

    if len(player_label_options) > 1:
        with st.form("old_world_league_result_form", clear_on_submit=True):
            c1, c_vs, c2 = st.columns([2, 0.35, 2])
            league_faction_options = ["— None —", *PLACEHOLDER_FACTIONS]
            painting_bonus_options = ["— None —", "Partially Painted", "Fully Painted"]
            with c1:
                player_1_label = st.selectbox("Player 1", player_label_options, index=0, key="owl_results_player_1")
                player_1_faction_choice = st.selectbox("Player 1 Faction", league_faction_options, index=0, key="owl_results_player_1_faction")
                player_1_painting_bonus_choice = st.selectbox("Player 1 Painting Bonus", painting_bonus_options, index=0, key="owl_results_player_1_painting_bonus")
            with c_vs:
                st.markdown("<div style='text-align:center;font-weight:700;padding-top:2.1rem'>vs</div>", unsafe_allow_html=True)
            with c2:
                player_2_label = st.selectbox("Player 2", player_label_options, index=0, key="owl_results_player_2")
                player_2_faction_choice = st.selectbox("Player 2 Faction", league_faction_options, index=0, key="owl_results_player_2_faction")
                player_2_painting_bonus_choice = st.selectbox("Player 2 Painting Bonus", painting_bonus_options, index=0, key="owl_results_player_2_painting_bonus")

            game_type_choice = st.selectbox(
                "Game Type",
                ["Casual", "Competitive"],
                index=1,
                key="owl_results_game_type",
                help="Casual uses K=10; Competitive uses K=40 for ELO changes.",
            )
            result_choice = st.selectbox(
                "Result",
                ["Player 1 Victory", "Player 2 Victory", "Draw"],
                index=0,
                key="owl_results_result",
            )
            submitted_league_result = st.form_submit_button("Submit Result")

        if submitted_league_result:
            if player_1_label == "— None —" or player_2_label == "— None —":
                st.error("Please select both players before submitting a result.")
            elif player_1_label == player_2_label:
                st.error("Please select two different players before submitting a result.")
            else:
                player_1_id = player_label_to_id.get(player_1_label)
                player_2_id = player_label_to_id.get(player_2_label)
                player_1_name = player_id_to_name.get(player_1_id, player_1_label)
                player_2_name = player_id_to_name.get(player_2_id, player_2_label)
                player_1_faction = None if player_1_faction_choice == "— None —" else player_1_faction_choice
                player_2_faction = None if player_2_faction_choice == "— None —" else player_2_faction_choice
                player_1_painting_bonus = None if player_1_painting_bonus_choice == "— None —" else player_1_painting_bonus_choice
                player_2_painting_bonus = None if player_2_painting_bonus_choice == "— None —" else player_2_painting_bonus_choice

                ensure_league_results_table()
                result_date_clean = uk_date_str(date.today())

                with Session(engine) as s:
                    # Guard against accidental double-clicks: if this exact
                    # league result has already been submitted today, do not
                    # create a second copy. Different results or rematches can
                    # still be submitted intentionally.
                    existing_result = s.exec(
                        select(LeagueResult).where(
                            (LeagueResult.player_1_id == player_1_id)
                            & (LeagueResult.player_2_id == player_2_id)
                            & (LeagueResult.result == result_choice)
                            & (LeagueResult.result_date == result_date_clean)
                            & (LeagueResult.player_1_faction == player_1_faction)
                            & (LeagueResult.player_2_faction == player_2_faction)
                            & (LeagueResult.player_1_painting_bonus == player_1_painting_bonus)
                            & (LeagueResult.player_2_painting_bonus == player_2_painting_bonus)
                            & (LeagueResult.game_type == game_type_choice)
                        )
                    ).first()

                    if existing_result:
                        st.info("This exact league result has already been submitted, so a duplicate was not created.")
                    else:
                        lr = LeagueResult(
                            player_1_id=player_1_id,
                            player_1_name=player_1_name,
                            player_2_id=player_2_id,
                            player_2_name=player_2_name,
                            player_1_faction=player_1_faction,
                            player_2_faction=player_2_faction,
                            player_1_painting_bonus=player_1_painting_bonus,
                            player_2_painting_bonus=player_2_painting_bonus,
                            game_type=game_type_choice,
                            result=result_choice,
                            result_date=result_date_clean,
                        )
                        s.add(lr)
                        s.commit()
                        recalc_league_ratings()
                        st.success("League result submitted and ELO rankings recalculated.")
    else:
        st.info("No player profiles found yet. Add players via the signup flow first.")


# --------------- Admin: Signups ---------------
if "Signups" in idx:
    with T[idx["Signups"]]:
        st.subheader("Browse Signups")
        sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_sys_su")

        week_lookup = st.text_input(
            "Week (DD/MM/YYYY)",
            value=week_id_for_system(sys_pick, date.today()),
            key=f"adm_week_su_{sys_pick}",
            help="The Old World = Wednesday date; The Horus Heresy and Kill Team = Friday date."
        )
        with Session(engine) as s:
            sus = s.exec(select(Signup).where((Signup.week == week_lookup) & (Signup.system == sys_pick)).order_by(Signup.created_at)).all()
        if not sus:
            st.info("No signups yet.")
        else:
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
                "Can Lead Intro": su.can_demo,
                "Created": su.created_at.strftime("%Y-%m-%d %H:%M")
            } for su in sus]
            df = pd.DataFrame(rows)
            # Make certain columns non-editable
            disabled_cols = ["ID", "Name", "Created"]
            edited = st.data_editor(
                df,
                width='stretch',
                hide_index=True,
                disabled=disabled_cols,
                key="signups_editor"
            )
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Save Changes"):
                    # Compare and persist changes back to DB
                    changes = 0
                    orig_map = {r["ID"]: r for r in rows}
                    with Session(engine) as s:
                        for _, r in edited.iterrows():
                            rid = int(r["ID"])
                            o = orig_map[rid]
                            fields = ["Faction","Pts","ETA","Exp","Type","Standby","T&T","Scenario","Can Lead Intro"]
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
                                    su.can_demo = bool(r["Can Lead Intro"]) if pd.notna(r["Can Lead Intro"]) else False
                                    s.add(su); changes += 1
                        if changes:
                            s.commit()
                            invalidate_app_caches()
                    if changes:
                        st.success(f"Saved {changes} row(s).")
                    else:
                        st.info("No changes detected.")
            with c2:
                del_ids = st.multiselect("Delete Signups (Select ID)", options=list(edited["ID"]))
                if st.button("Delete Selected") and del_ids:
                    with Session(engine) as s:
                        for rid in del_ids:
                            obj = s.get(Signup, int(rid))
                            if obj:
                                s.delete(obj)
                        s.commit()
                    invalidate_app_caches()
                    st.warning(f"Deleted {len(del_ids)} signup(s).")

# --------------- Admin: Pairings (merged Generate + Browse) ---------------
if "Pairings Admin" in idx:
    with T[idx["Pairings Admin"]]:

        # --- Shared system/week selector at the top ---
        c1, c2 = st.columns([1, 2])
        with c1:
            sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_sys_pairs")
        with c2:
            week_lookup = st.text_input(
                "Week (DD/MM/YYYY)",
                value=week_id_for_system(sys_pick, date.today()),
                key=f"adm_week_pairs_{sys_pick}",
                help="The Old World = Wednesday date; The Horus Heresy and Kill Team = Friday date."
            )
        week_val = week_lookup  # alias used by generate section below

        st.divider()

        # ---- Section 1: Generate Weekly Pairings ----
        st.subheader("Generate Weekly Pairings")
        st.caption("Deletes existing **pending** pairings for that week+system before generating.")
        allow_repeats = st.checkbox("Allow Rematches If Necessary", value=True)
        allow_tnt = st.checkbox("Enable 3-Way (T&T) Grouping When Odd Numbers", value=True, help="Creates a BYE record for the odd person.")

        if st.button("Generate Pairings", type="primary"):
            with Session(engine) as s:
                old = s.exec(select(Pairing).where((Pairing.week == week_val) & (Pairing.system == sys_pick) & (Pairing.status == "pending"))).all()
                for r in old:
                    s.delete(r)
                s.commit()
            created = generate_pairings_for_week(week_val, sys_pick, allow_repeats_when_needed=allow_repeats, allow_tnt=allow_tnt)
            invalidate_app_caches()
            if created:
                st.success(f"Created {len(created)} pairing(s).")
            else:
                st.info("No signups to pair.")

        st.divider()

        # ---- Section 2: Browse / Delete Pairings ----
        st.subheader("Browse / Delete Pairings")

        # Publish controls — fetch gate once; button handlers upsert then rerun (gate re-fetched on next render)
        with Session(engine) as s:
            gate = s.exec(
                select(PublishState).where(
                    (PublishState.week == week_lookup) & (PublishState.system == sys_pick)
                )
            ).first()

        col_p1, col_p2, col_p3 = st.columns([1, 1, 3])
        with col_p1:
            if st.button("Publish to Public"):
                with Session(engine) as s:
                    g = gate or PublishState(week=week_lookup, system=sys_pick)
                    s.merge(g) if g.id else s.add(g)
                    g.published = True
                    s.add(g); s.commit()
                invalidate_app_caches()
                st.success("Published.")
                st.rerun()
        with col_p2:
            if st.button("Unpublish"):
                with Session(engine) as s:
                    g = gate or PublishState(week=week_lookup, system=sys_pick)
                    g.published = False
                    s.add(g); s.commit()
                invalidate_app_caches()
                st.warning("Unpublished.")
                st.rerun()
        with col_p3:
            st.caption(f"Public status: **{'Published' if (gate and gate.published) else 'Not Published'}**")

        
        with Session(engine) as s:
            # Load pairings for this week+system
            prs = s.exec(
                select(Pairing)
                .where((Pairing.week == week_lookup) & (Pairing.system == sys_pick))
                .order_by(Pairing.id)
            ).all()
            # Load all signups for dropdown options
            sus = s.exec(
                select(Signup).where(
                    (Signup.week == week_lookup) & (Signup.system == sys_pick)
                )
            ).all()

        if not prs:
            st.info("No pairings.")
        else:
            # Helper to label signups in dropdowns
            def _label_signup(su: Signup | None) -> str:
                if not su:
                    return ""
                name = (su.player_name or "").strip() or "Unnamed"
                return f"{su.id} — {name}"

            signup_by_id = {su.id: su for su in sus}
            all_labels = [_label_signup(su) for su in sus]
            bye_label = "BYE"

            public_rows_for_discord: List[dict] = []

            tnt_names = set(TNT_SUGGESTIONS.get((week_lookup, sys_pick), []))
            rows = []
            for p in prs:
                a = signup_by_id.get(p.a_signup_id)
                b = signup_by_id.get(p.b_signup_id) if p.b_signup_id else None

                eta_show = _eta_show_for_pair(a, b)
                pts_show = _pts_show_for_pair(a, b)

                type_show = _public_vibe_display(getattr(a, "vibe", None), getattr(b, "vibe", None))
                if sys_pick == "The Old World" and tnt_names:
                    if (a and a.player_name in tnt_names) or (b and b.player_name in tnt_names):
                        type_show = "T&T"

                public_rows_for_discord.append({
                    "A": a.player_name if a else f"A#{p.a_signup_id}",
                    "Faction A": (p.a_faction or (a.faction if a else None)),
                    "B": (b.player_name if b else "BYE"),
                    "Faction B": ((p.b_faction or (b.faction if b else None)) if b else None),
                    "Type": type_show,
                    "ETA": eta_show,
                    "Points": pts_show,
                })

                rows.append({
                    "ID": p.id,
                    "A": _label_signup(a),
                    "A Faction": (p.a_faction or (a.faction if a else None)),
                    "A Type": (a.vibe if a else None),
                    "B": (_label_signup(b) if b else bye_label),
                    "B Faction": ((p.b_faction or (b.faction if b else None)) if b else None),
                    "B Type": ((b.vibe if b else None) if b else None),
                    "ETA": eta_show,
                    "Points": pts_show,
                })

            df_admin_pairs = pd.DataFrame(rows)

            edited = st.data_editor(
                df_admin_pairs,
                width='stretch',
                hide_index=True,
                key="pairings_editor_admin",
                column_config={
                    "ID": st.column_config.NumberColumn("ID", disabled=True),
                    "A": st.column_config.SelectboxColumn(
                        "A",
                        options=all_labels,
                        help="Choose which signup is player A",
                    ),
                    "A Faction": st.column_config.SelectboxColumn(
                        "A Faction",
                        options=(HH_FACTIONS_WITH_BLANK if sys_pick == "The Horus Heresy" else PLACEHOLDER_FACTIONS_WITH_BLANK),
                    ),
                    "A Type": st.column_config.SelectboxColumn(
                        "A Type",
                        options=(["Standard", "Intro"] if sys_pick == "The Horus Heresy" else ["Casual", "Competitive", "Intro", "Either"]),
                    ),
                    "B": st.column_config.SelectboxColumn(
                        "B",
                        options=[bye_label] + all_labels,
                        help="Choose which signup is player B (or BYE)",
                    ),
                    "B Faction": st.column_config.SelectboxColumn(
                        "B Faction",
                        options=(HH_FACTIONS_WITH_BLANK if sys_pick == "The Horus Heresy" else PLACEHOLDER_FACTIONS_WITH_BLANK),
                    ),
                    "B Type": st.column_config.SelectboxColumn(
                        "B Type",
                        options=(["Standard", "Intro"] if sys_pick == "The Horus Heresy" else ["Casual", "Competitive", "Intro", "Either"]),
                    ),
                    "Type": st.column_config.SelectboxColumn(
                        "Type",
                        options=(["Standard", "Intro"] if sys_pick == "The Horus Heresy" else ["Casual", "Competitive", "Intro", "Either"]),
                    ),
                    "ETA": st.column_config.SelectboxColumn(
                        "ETA",
                        options=[f"{h:02d}:{m:02d}" for h in [17, 18, 19] for m in [0, 15, 30, 45] if not (h == 19 and m > 30)],
                    ),
                    "Points": st.column_config.NumberColumn("Points"),
                },
            )

            st.caption("Use the dropdowns in 'A' and 'B' to manually re-pair matches in this week/system.")

            # Save button: persist changes back to DB
            if st.button("Save Pairing Changes", type="primary"):
                def parse_signup_id(label: str | None) -> int | None:
                    if not label or label == bye_label:
                        return None
                    # Expect format "123 — Name"
                    try:
                        return int(str(label).split("—", 1)[0].strip())
                    except Exception:
                        return None

                changed = 0
                with Session(engine) as s:
                    for _, row in edited.iterrows():
                        pid = int(row["ID"])
                        p = s.get(Pairing, pid)
                        if not p:
                            continue

                        new_a_id = parse_signup_id(row["A"])
                        new_b_id = parse_signup_id(row["B"])
                        new_type = row["Type"] if "Type" in row else None
                        new_eta = row["ETA"] if "ETA" in row else None
                        new_pts_raw = row["Points"] if "Points" in row else None
                        new_a_type = row["A Type"] if "A Type" in row else None
                        new_b_type = row["B Type"] if "B Type" in row else None

                        # Normalise points
                        new_pts = None
                        try:
                            if new_pts_raw is not None and str(new_pts_raw) != "" and not (isinstance(new_pts_raw, float) and math.isnan(new_pts_raw)):
                                new_pts = int(new_pts_raw)
                        except Exception:
                            new_pts = None

                        new_a_faction = row.get("A Faction")
                        new_b_faction = row.get("B Faction")

                        p.a_signup_id = new_a_id
                        p.b_signup_id = new_b_id

                        a_su = s.get(Signup, new_a_id) if new_a_id else None
                        b_su = s.get(Signup, new_b_id) if new_b_id else None

                        # Factions: prefer edited dropdown, sync back to Signup
                        if a_su:
                            if pd.notna(new_a_faction):
                                a_su.faction = None if new_a_faction == "— None —" else str(new_a_faction)
                            p.a_faction = a_su.faction
                            s.add(a_su)
                        else:
                            p.a_faction = None

                        if b_su:
                            if pd.notna(new_b_faction):
                                b_su.faction = None if new_b_faction == "— None —" else str(new_b_faction)
                            p.b_faction = b_su.faction
                            s.add(b_su)
                        else:
                            p.b_faction = None

                        # Types: prefer per-player A/B type if provided; fall back to shared Type
                        if a_su:
                            if "A Type" in row and pd.notna(new_a_type) and str(new_a_type).strip():
                                a_su.vibe = str(new_a_type)
                            elif new_type:
                                a_su.vibe = new_type
                            s.add(a_su)

                        if b_su:
                            if "B Type" in row and pd.notna(new_b_type) and str(new_b_type).strip():
                                b_su.vibe = str(new_b_type)
                            elif new_type:
                                b_su.vibe = new_type
                            s.add(b_su)

                        # ETA: write back to both players
                        if new_eta:
                            if a_su:
                                a_su.eta = new_eta
                                s.add(a_su)
                            if b_su:
                                b_su.eta = new_eta
                                s.add(b_su)

                        # Points: write back to both players
                        if new_pts is not None:
                            if a_su:
                                a_su.points = new_pts
                                s.add(a_su)
                            if b_su:
                                b_su.points = new_pts
                                s.add(b_su)

                        s.add(p)
                        changed += 1

                    if changed:
                        s.commit()

                if changed:
                    st.success(f"Saved {changed} pairing(s).")
                else:
                    st.info("No changes detected.")

            # Discord: post public-style pairings table to webhook, if configured
            if DISCORD_PAIRINGS_WEBHOOK_URL:
                if st.button("Post Pairings to Discord"):
                    if public_rows_for_discord:
                        post_pairings_table_to_discord(public_rows_for_discord, week_lookup, sys_pick)
                        st.success("Posted pairings to Discord.")
                    else:
                        st.warning("No pairings to post to Discord.")
            else:
                st.caption("Configure DISCORD_PAIRINGS_WEBHOOK_URL to enable Discord pairings posting.")


            with st.form("delete_pairs_form", clear_on_submit=True):
                ids_str = st.text_input("Delete Pairing IDs (Comma-Separated)")
                do_delete = st.form_submit_button("Delete Selected")
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
# --------------- Admin: League ---------------
if "League" in idx:
    with T[idx["League"]]:
        st.markdown("### Submitted Games")

        ensure_league_results_table()

        recalc_col, _ = st.columns([1, 3])
        with recalc_col:
            if st.button("Recalculate ELO Ratings"):
                recalc_league_ratings()
                st.success("League ELO ratings recalculated from full result history.")

        league_rows = league_submitted_games_rows()

        if not league_rows:
            st.info("No league results have been submitted yet.")
        else:
            st.dataframe(league_rows, width='stretch', hide_index=True)

            delete_result_ids = st.multiselect(
                "Delete Results (Select Game Number)",
                options=[row["Game Number"] for row in league_rows],
            )
            if st.button("Delete Selected Result(s)") and delete_result_ids:
                with Session(engine) as s:
                    for rid in delete_result_ids:
                        obj = s.get(LeagueResult, int(rid))
                        if obj:
                            s.delete(obj)
                    s.commit()
                recalc_league_ratings()
                st.warning(f"Deleted {len(delete_result_ids)} league result(s) and recalculated ELO ratings.")


# --------------- Admin: View History ---------------
if "View History" in idx:
    with T[idx["View History"]]:
        st.subheader("View History")
        sys_pick = st.selectbox("System", SYSTEMS, index=0, key="adm_hist_sys")
        week_filter = st.text_input("Week Contains (Optional)", value="", key="adm_hist_week_filter")
        limit = st.number_input("Show Last N Pairings", min_value=10, max_value=1000, value=200, step=10, help="Caps how many rows to display")

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

                limited_prs = prs[:limit]
                signup_ids = {p.a_signup_id for p in limited_prs}
                signup_ids.update({p.b_signup_id for p in limited_prs if p.b_signup_id})
                signup_by_id = {
                    su.id: su
                    for su in s.exec(select(Signup).where(Signup.id.in_(signup_ids))).all()
                } if signup_ids else {}

                for p in limited_prs:
                    a = signup_by_id.get(p.a_signup_id)
                    b = signup_by_id.get(p.b_signup_id) if p.b_signup_id else None

                    eta_show = _eta_show_for_pair(a, b)
                    pts_show = _pts_show_for_pair(a, b)

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
                            "ETA": eta_show,
                        "Points": pts_show,
                    })

            df = pd.DataFrame(rows)
            st.dataframe(df, width='stretch', hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download History as CSV", data=csv, file_name="pairings_history.csv", mime="text/csv", width='stretch')



