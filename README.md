# Call to Arms — Streamlit + Supabase Setup (Simple Guide)

This guide helps you host your `pairings.py` app using Supabase as the database and Streamlit for the interface.

## 1. Required Files
- `pairings.py` (your app)
- `requirements.txt`
- `.gitignore`
- `.streamlit/secrets.toml` (local only; not committed)

## 2. Get Your Supabase Connection String
In Supabase → **Project Settings → Database → Connection Info**  
Copy and update it like this:
```
postgresql+psycopg2://postgres:YOUR_PASSWORD@YOUR_HOST.supabase.co:5432/postgres?sslmode=require
```

## 3. Local Setup (optional)
```bash
pip install -r requirements.txt
mkdir -p .streamlit
# then create .streamlit/secrets.toml with:
DATABASE_URL = "postgresql+psycopg2://postgres:YOUR_PASSWORD@YOUR_HOST.supabase.co:5432/postgres?sslmode=require"
ADMIN_PASSWORD = "your-admin-password"
streamlit run pairings.py
```

## 4. Deploy to Streamlit Cloud
1. Push to GitHub (`pairings.py`, `requirements.txt`, `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io) and link your repo
3. Add this in **App → Settings → Secrets**:
   ```toml
   DATABASE_URL = "postgresql+psycopg2://postgres:YOUR_PASSWORD@YOUR_HOST.supabase.co:5432/postgres?sslmode=require"
   ADMIN_PASSWORD = "your-admin-password"
   ```
4. Deploy — the app creates tables automatically.

## 5. Notes
- `ADMIN_PASSWORD` unlocks the admin view in the sidebar.
- Use **Publish/Unpublish** in the Admin tab to control public visibility.
- The app uses Supabase Postgres automatically if DATABASE_URL is present, otherwise local SQLite.

## 6. Troubleshooting
- Check DATABASE_URL for typos or missing `?sslmode=require`
- Ensure Python ≥ 3.10
- Verify tables created correctly in Supabase via the SQL Editor
