# DSVV News — Setup

Python 3.13 Flask app backed by **MongoDB** (via MongoEngine). Ships with a
server-rendered admin UI and a JWT-protected JSON API in the same app.

## Prerequisites

- Python 3.11+ (3.13 recommended; all deps have cp313 wheels).
- MongoDB 6+ (local install, Docker, or Atlas — pick one below).
- Git.

## 1. Pick a MongoDB option

### Option A — MongoDB Atlas (easiest, free tier)

1. Sign up at <https://www.mongodb.com/atlas> and create a free **M0** cluster.
2. Under *Network Access*, allow your IP (or `0.0.0.0/0` for dev only).
3. Under *Database Access*, create a user with a password.
4. Click *Connect → Drivers → Python* and copy the connection string.
5. Put it in `.env` as `MONGODB_HOST`, e.g.
   ```
   MONGODB_HOST=mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/dsvv_news?retryWrites=true&w=majority
   ```

### Option B — Local install (Windows)

1. Download *MongoDB Community Server* from
   <https://www.mongodb.com/try/download/community>.
2. Run the installer and choose **"Install MongoDB as a Service"**.
3. Start it from an elevated PowerShell / cmd:
   ```powershell
   net start MongoDB
   ```
4. Leave `MONGODB_HOST=mongodb://localhost:27017/dsvv_news` in `.env`.

### Option C — Docker

```bash
docker run -d --name dsvv-mongo -p 27017:27017 -v dsvv_mongo_data:/data/db mongo:7
```

## 2. Install the app

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env and set MONGODB_HOST (and SECRET_KEY / JWT_SECRET_KEY for real deployments)
python scripts/seed.py
python run.py
```

The dev server binds to <http://localhost:5000>.

## 3. Default login

The seed script creates three roles (`writer`, `editor`, `admin`) and one admin:

- **Email:** `admin@dsvv.ac.in`
- **Password:** `ChangeMe123!`

Override via `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` in `.env` before
running `scripts/seed.py`.

## URL map

| Path                          | Purpose                                  |
| ----------------------------- | ---------------------------------------- |
| `/` and `/news`               | Public homepage (News18-style)           |
| `/news/category/<slug>`       | Category landing page                    |
| `/news/<slug>`                | Public article detail                    |
| `/login`                      | CMS sign-in                              |
| `/dashboard`                  | Newsroom dashboard (requires login)      |
| `/posts`, `/alumni`, `/media` | Admin modules                            |
| `/api/*`                      | JSON API (JWT auth, see `app/routes/`)   |

## Notes

- MongoEngine creates indexes lazily on first query — no migrations needed.
- Collections are created on demand; there is no schema file to apply.
- The legacy SQLite file at `instance/dsvv_news.db` is obsolete and can be
  deleted.

## Quick MongoDB sanity check

```bash
mongosh --eval "db.adminCommand('ping')"
```

Or open *MongoDB Compass* and connect to your `MONGODB_HOST`.
