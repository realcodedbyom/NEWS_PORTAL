# Codebuff Knowledge — DSVV News Portal

> **Read this first.** This is the single source of truth for any agent working on this repo. If something here contradicts the code, the code wins — update this file.

---

## 1. TL;DR

**What it is:** A News18-India-style news portal for Dev Sanskriti Vishwavidyalaya (Haridwar).
**Stack:** Flask 3 + MongoDB (via MongoEngine) + Cloudinary + Jinja + APScheduler.
**Runs on:** Python 3.13 (Windows dev box at `D:\om\projects\News_portal`).
**Public site theme:** AWGP / Shantikunj — brand blue `#1c4c94` + saffron accent `#fdc82c`. Breaking-news ticker stays red (`#EE1C25`) by design.
**Content source:** `scripts/scrape_awgp.py` imports real articles from awgp.org, mirrors images to Cloudinary, sanitizes HTML with bleach.

---

## 2. How to run anything (Windows / bash shell)

All commands assume CWD = project root.

```bash
# Activate venv (always prefix python calls with venv path — do NOT rely on PATH)
venv/Scripts/python.exe ...

# Sanity: does the app import?
venv/Scripts/python.exe -c "from app import create_app; a=create_app(); print('OK', len(a.blueprints))"

# Compile-check everything
venv/Scripts/python.exe -m compileall -q app scripts

# Dev server (binds 0.0.0.0:8000)
venv/Scripts/python.exe run.py

# Seed roles + admin (idempotent)
venv/Scripts/python.exe scripts/seed.py

# Scrape 50 awgp.org articles (WIPES posts by default)
venv/Scripts/python.exe scripts/scrape_awgp.py --limit 50
venv/Scripts/python.exe scripts/scrape_awgp.py --no-wipe     # append
venv/Scripts/python.exe scripts/scrape_awgp.py --quiet       # less noise

# Test client render check (no browser needed)
venv/Scripts/python.exe -c "from dotenv import load_dotenv; load_dotenv('.env', override=True)
from app import create_app
app=create_app(); c=app.test_client()
for p in ['/news','/news/category/news']:
    print(p, c.get(p).status_code)"
```

**There are no tests, no linter, no typechecker configured.** Validate changes via `compileall` + app-import + test-client render.

---

## 3. Project layout (essentials only)

```
News_portal/
├── app/
│   ├── __init__.py              # create_app() factory
│   ├── config.py                # env-driven config
│   ├── extensions.py            # JWT, CORS, CSRF, scheduler, Mongo
│   ├── models/                  # MongoEngine Documents
│   │   ├── user.py · role.py · post.py · tag.py
│   │   ├── media.py · alumni.py · analytics.py · base.py
│   ├── services/                # business logic (post, auth, media, alumni, analytics, scheduler)
│   ├── controllers/             # thin HTTP → service glue
│   ├── routes/                  # blueprints
│   │   ├── auth.py · posts.py · users.py · media.py
│   │   ├── alumni.py · analytics.py · health.py
│   │   └── web.py               # server-rendered UI + public newsroom
│   ├── utils/
│   │   ├── enums.py             # PostStatus, PostCategory, RoleName, ALLOWED_TRANSITIONS
│   │   ├── decorators.py · pagination.py · responses.py
│   │   ├── slug.py · validators.py · exceptions.py
│   ├── templates/
│   │   ├── base.html            # admin shell
│   │   ├── dashboard.html
│   │   ├── auth/login.html
│   │   ├── public/              # PUBLIC SITE — touch these for user-facing work
│   │   │   ├── home.html · detail.html · category.html
│   │   │   ├── search.html · _header.html
│   │   ├── posts/ · alumni/ · media/ · users/ · errors/
│   └── static/css/
│       ├── public.css           # public site (News18-style, now AWGP blue+saffron)
│       └── main.css             # admin CMS
├── scripts/
│   ├── seed.py                  # roles + bootstrap admin (idempotent)
│   └── scrape_awgp.py           # awgp.org → Cloudinary → Mongo
├── run.py                       # dev entry
├── wsgi.py                      # gunicorn entry
├── requirements.txt
├── .env.example                 # template
├── .env                         # LOCAL ONLY, gitignored, has real secrets
├── README.md · SETUP.md · codebuff.md (this file)
└── venv/                        # gitignored
```

**Gitignored (do NOT commit):** `.env`, `venv/`, `__pycache__/`, `instance/`, `uploads/`, `_*.txt`, `_*.html`, `*.log`, `node_modules/`, `package*.json`.

---

## 4. Domain model cheat sheet

### Roles (`app/utils/enums.py::RoleName`)
- `writer` — create/edit own drafts, submit for review
- `editor` — approve/reject, move to ready-to-publish
- `admin` — publish, archive, manage users

### Post categories (`PostCategory`)
`news · culture · academics · announcements · events · research`

### Post statuses (`PostStatus`)
```
draft · review (legacy) · pending_review · in_review
changes_required · approved · ready_to_publish
published · rejected · rejected_public · archived
```

### Workflow (`ALLOWED_TRANSITIONS` in `enums.py` is the ONLY source of truth)
```
Internal:  draft → in_review → approved → ready_to_publish → published → archived
                                            │
                                            ├→ changes_required → draft
                                            └→ rejected → draft

Public (via /submit):  pending_review → in_review → approved → ready_to_publish → published
                                     └→ rejected_public → archived | draft
```

Every transition appends to `post.status_history[]`. Every save creates a `PostVersion` snapshot.

---

## 5. URL map (quick lookup)

| Path | Purpose |
|---|---|
| `/` and `/news` | Public homepage |
| `/news/category/<slug>` | Category landing |
| `/news/<slug>` | Article detail |
| `/news/search?q=...` | Search |
| `/submit` | Public submission (login required, 5/24h cap) |
| `/login` · `/logout` · `/dashboard` | CMS auth + shell |
| `/my-submissions` | Contributor status tracker |
| `/cms/notifications` · `/cms/public-queue` · `/cms/review-queue` | Moderation UI |
| `/posts` · `/posts/new` · `/posts/<id>/edit` | Post admin |
| `/alumni` · `/media` · `/users` | Directory admins |
| `/api/*` | JWT JSON API |
| `/api/health` | Liveness |

---

## 6. JSON API envelope (consistent everywhere)

```json
// Success
{ "success": true, "data": {...}, "message": "...", "meta": { "page":1, "per_page":20, "total":0, "pages":0, "has_next":false, "has_prev":false } }

// Error
{ "success": false, "message": "Not found", "details": null }
```

IDs are always ObjectId hex strings (URLs, JSON, JWT identity).

---

## 7. Conventions — follow these or your PR will look weird

- **Models** declare indexes in `meta = { ... }`. No migrations — MongoEngine creates indexes lazily.
- **Services** hold business logic. Controllers stay thin (orchestration only).
- **Routes** register blueprints, call controllers, never touch `Document.objects` directly.
- **Workflow rules** → only change `ALLOWED_TRANSITIONS`. Never hardcode status checks in services.
- **Template structure** — public site uses `public/*.html`, admin uses `base.html` + module folders.
- **CSS tokens** — use CSS variables in `public.css`:
  - `--brand-primary: #1c4c94` (AWGP blue)
  - `--brand-accent: #fdc82c` (saffron)
  - `--breaking-red: #EE1C25` (ticker ONLY — do NOT reuse elsewhere)
  - Legacy `--brand-red*` tokens are aliased to blue for backward compat; prefer `--brand-primary` in new rules.
- **No `any` types**, no broad `except:` — always name the exception.
- **Cloudinary only for images** — never serve from `/uploads/`; that folder is gitignored and empty.

---

## 8. Env vars (`.env`) — required

```
SECRET_KEY=<strong-random>
JWT_SECRET_KEY=<strong-random>
MONGODB_HOST=mongodb://... (or Atlas URI)
MONGODB_DB=dsvv_news
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
CLOUDINARY_UPLOAD_FOLDER=dsvv_news
ADMIN_EMAIL=admin@dsvv.ac.in
ADMIN_PASSWORD=ChangeMe123!
```

App will **refuse to start** without Cloudinary creds. See `.env.example` for the full list.

---

## 9. Recent work log (most recent first)

Lets agents know what's already been done so they don't redo it.

### 2024-Q4 — AWGP/Shantikunj rebrand
- Switched public theme from news-red to AWGP blue `#1c4c94` + saffron `#fdc82c`.
- Breaking-news strip preserved in red via `--breaking-red`.
- Updated `<meta name="theme-color">` to blue in `home.html`, `detail.html`, `category.html`, `search.html`.
- Legacy `--brand-red*` tokens aliased to blue so ~40 downstream rules inherit automatically.

### 2024-Q4 — Directory cleanup before first real git commit
- Deleted scratch files (`_body.txt`, `_card.txt`, `_cv.txt`, `_detail.html`, `_list.html`).
- Removed stray Node cruft (`package.json`, `package-lock.json`, `node_modules/`, `uploads/`).
- Untracked `.env`, `instance/dsvv_news.db` (SQLite legacy — deleted), all `__pycache__/*.pyc` from git.
- Rewrote `.gitignore` from scratch with proper Python/Flask rules.
- Updated `README.md` + `SETUP.md` (dropped 12-demo-posts claim, documented `scrape_awgp.py` flags).

### 2024-Q4 — Scraper + content cleanup hardening
- `scripts/scrape_awgp.py::_clean_body()` now decomposes `<script>`, `<style>`, `<iframe>`, `<form>`, awgp.org UI widgets BEFORE bleach (bleach alone leaks them as plaintext).
- Strips awgp-specific junk: `sharePage`, `×`, `Get More`, `Read More`, `Phots` (sic) typo, `NewsPostHander`, `PopulateNext`, etc.
- Defensive iteration: guards against orphaned/decomposed tags via `el.parent is None` checks.
- Mobile CSS: safety-net `max-width:100%` on article images, nav gets fade-gradient + `scroll-snap-type` so categories are discoverable.
- Removed fake view counts from home/detail/category/search templates.
- `_nav_categories()` in `web.py` only returns categories that have live posts, and only runs on newsroom pages (not admin) to save a `distinct()` query.
- Gallery section added to `detail.html` for posts with multiple images.

---

## 10. Gotchas / lessons learned

- **awgp.org is fragile.** `_clean_body` is defensive for a reason — BeautifulSoup `.decompose()` during iteration leaves orphaned refs; always guard with `el.parent is None`.
- **bleach strips tags but keeps inner text** — that's why we decompose `<script>`/`<style>` with BeautifulSoup first.
- **Windows paths matter.** Use `venv/Scripts/python.exe` in commands, not `python`. Forward slashes work in bash shell.
- **Git history still has `.env`.** Rotate `SECRET_KEY`, `JWT_SECRET_KEY`, `CLOUDINARY_API_SECRET`, MongoDB password before making the repo public. `.env` is now gitignored but prior commits hold the old values.
- **`instance/dsvv_news.db` is dead.** App uses MongoDB only. Don't resurrect SQLite.
- **Flask context processor runs on every render** — gate expensive queries to the endpoints that actually need them (see `_inject_globals` in `web.py`).
- **Scraper wipes by default.** Always pass `--no-wipe` if you want to preserve existing posts.

---

## 11. Working with other agents on this repo

- **Before editing**, always read the target file(s) first. The editor agent cannot read files on its own.
- **Reuse services / helpers** instead of re-implementing. Check `app/services/` and `app/utils/` first.
- **Respect the color tokens.** Don't hardcode hex colors in new CSS — use `var(--brand-primary)` etc. The breaking-news strip is the only place that should reference red.
- **Don't add packages via `package.json` or `pip install`** without user approval. Current deps are pinned in `requirements.txt`.
- **When in doubt, ask the user.** Use `ask_user` for any non-obvious UX / schema decision.

---

## 12. Quick task recipes

### Add a new post category
1. Add to `PostCategory` enum in `app/utils/enums.py`.
2. No migration needed (MongoEngine).
3. Update `_nav_categories` if needed (auto-handled — it reads `PostCategory.values()`).
4. Add a hero image / copy override in `app/templates/public/category.html` if the default looks bad.

### Add a new workflow state
1. Add to `PostStatus` enum.
2. Add rows in `ALLOWED_TRANSITIONS` (both inbound + outbound).
3. Update `app/templates/posts/form.html` status dropdown if writers need to pick it.
4. Update `app/services/post_service.py` if the state has special side-effects (notifications, publishing, etc.).

### Re-theme the public site
1. Edit CSS variables at the top of `app/static/css/public.css`.
2. Update `<meta name="theme-color">` in all four `public/*.html` templates.
3. Don't touch `.breaking-chip`, `.breaking-marquee` — those use `--breaking-red` on purpose.

### Add an API endpoint
1. Define route in `app/routes/<blueprint>.py`.
2. Add controller in `app/controllers/<area>_controller.py`.
3. Put business logic in `app/services/<area>_service.py`.
4. Use the standard JSON envelope via `app/utils/responses.py` helpers.

---

*Last updated: after the AWGP/Shantikunj theme switch. Keep this file current — it's the agents' lifeline.*
