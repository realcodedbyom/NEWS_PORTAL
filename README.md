<div align="center">

# DSVV News

**A News18-India-style news portal for Dev Sanskriti Vishwavidyalaya**

Flask · MongoDB · Server-rendered admin CMS + JSON API

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-6%2B-47A248?logo=mongodb&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Screenshots](#screenshots)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [URL Map](#url-map)
- [Editorial Workflow](#editorial-workflow)
- [JSON API](#json-api)
- [Seed Data](#seed-data)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Overview

**DSVV News** is a full-stack news portal for *Dev Sanskriti Vishwavidyalaya* (Haridwar). The public site mimics the look and feel of News18 India — red/white masthead, sticky navigation, breaking-news ticker, hero + top-stories block, per-category rails — but focuses on college news only (no Live TV / Video section).

Behind it sits a role-based editorial CMS with a multi-stage publishing workflow (draft → review → approved → ready → published), scheduled publishing, media library, alumni directory, and analytics.

## Screenshots

Drop screenshots into `docs/screenshots/` with the filenames below to have them render here.

<div align="center">

<table>
  <tr>
    <td align="center">
      <img src="docs/screenshots/home.png" width="420" alt="Public homepage (News18-style)"><br/>
      <sub><b>Public homepage</b> — hero, top stories, breaking ticker</sub>
    </td>
    <td align="center">
      <img src="docs/screenshots/category.png" width="420" alt="Category landing page"><br/>
      <sub><b>Category page</b> — grid of stories per section</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="docs/screenshots/detail.png" width="420" alt="Article detail page"><br/>
      <sub><b>Article detail</b> — breadcrumbs, share bar, related posts</sub>
    </td>
    <td align="center">
      <img src="docs/screenshots/dashboard.png" width="420" alt="Newsroom dashboard"><br/>
      <sub><b>Newsroom dashboard</b> — role-based CMS workflow</sub>
    </td>
  </tr>
</table>

</div>

## Features

### Public site (News18-style)
- Red masthead with DSVV branding and in-page search
- Sticky red navigation with category links
- Live-pulse **breaking news** marquee (respects `prefers-reduced-motion`)
- Hero story + numbered "Top Stories" aside
- Horizontally scrollable "Latest News" rail
- Per-category sections with "View All" links
- "Most Read" trending strip
- Accessible article detail page with breadcrumbs, share buttons (FB / X / WhatsApp / copy), and a "More in this category" sidebar

### Newsroom CMS
- JWT + session auth with CSRF for server-rendered forms
- Three built-in roles: `writer`, `editor`, `admin`
- Workflow engine with centrally-declared `ALLOWED_TRANSITIONS`
- Version history snapshots on every save
- Scheduled publishing via APScheduler (cron-free)
- Announcement / pinned / expiry flags
- Tag auto-creation, featured image, photo gallery
- Alumni directory with search
- Media library with image/video/document types
- Per-post analytics (views, referers)

### Developer experience
- Flask application factory + blueprints
- MongoEngine `Document`s with declarative indexes (no migrations)
- Marshmallow schemas for API validation
- Thin controllers → service layer → model pattern
- Consistent JSON error envelope across the API

## Tech Stack

| Layer | Technology |
| --- | --- |
| Runtime | Python 3.11+ (3.13 recommended) |
| Web framework | Flask 3 |
| Database | MongoDB 6+ via **MongoEngine** |
| Auth | Flask-JWT-Extended (API) · Flask-WTF / CSRF (admin) |
| Validation | Marshmallow |
| Templating | Jinja2 |
| Scheduling | APScheduler (background) |
| Images | Pillow |
| Production server | Gunicorn |

## Project Structure

```
News_portal/
├── app/
│   ├── __init__.py            # Application factory
│   ├── config.py              # Env-driven config classes
│   ├── extensions.py          # JWT, CORS, CSRF, scheduler, Mongo init
│   ├── models/                # MongoEngine Document schemas
│   │   ├── user.py · role.py · post.py · tag.py
│   │   ├── media.py · alumni.py · analytics.py · base.py
│   ├── services/              # Business logic (post, auth, media, alumni, analytics, scheduler)
│   ├── controllers/           # Thin HTTP orchestration
│   ├── routes/                # Blueprints (auth, posts, users, media, alumni, analytics, health, web)
│   ├── utils/                 # enums, decorators, pagination, slug, validators, responses, exceptions
│   ├── templates/             # Jinja templates (base, public/, posts/, alumni/, users/, media/, auth/)
│   └── static/css/            # public.css (News18 theme), main.css (admin)
├── docs/
│   └── screenshots/            # README images (see Screenshots section)
├── scripts/seed.py            # Roles + admin + 12 demo posts
├── run.py                     # Dev server entry
├── wsgi.py                    # Gunicorn entry
├── requirements.txt
├── .env.example
└── SETUP.md                   # Detailed setup walkthrough
```

## Quick Start

### 1. Clone & create a virtualenv

```powershell
git clone <your-repo-url> News_portal
cd News_portal
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start MongoDB

Pick one. Full instructions in [`SETUP.md`](./SETUP.md).

- **Atlas (cloud, free):** create an M0 cluster, copy the connection string into `MONGODB_HOST`.
- **Windows local:** install MongoDB Community Server → `net start MongoDB`.
- **Docker:** `docker run -d --name dsvv-mongo -p 27017:27017 -v dsvv_mongo_data:/data/db mongo:7`

### 3. Configure env

```powershell
copy .env.example .env
# edit .env and set MONGODB_HOST, SECRET_KEY, JWT_SECRET_KEY
```

### 4. Seed & run

```powershell
python scripts/seed.py
python run.py
```

Open <http://localhost:8000>. Log in at `/login` with:

- **Email:** `admin@dsvv.ac.in`
- **Password:** `ChangeMe123!`

> Override the admin credentials via `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` in `.env` before seeding.

## Configuration

All config reads from environment variables (via `python-dotenv`). The full list with defaults lives in `app/config.py`.

**Core**
: `SECRET_KEY` — Flask secret (sessions, CSRF). **Set this in production.**
: `FLASK_CONFIG` — `development` (default) · `testing` · `production`

**MongoDB**
: `MONGODB_DB` — database name (default: `dsvv_news`). The value from your `.env` always takes precedence over the in-code fallback.
: `MONGODB_HOST` — full Mongo connection URI

**JWT**
: `JWT_SECRET_KEY` — JWT signing key (falls back to `SECRET_KEY`)
: `JWT_ACCESS_TOKEN_EXPIRES_MIN` — access-token TTL in minutes (default: `60`)
: `JWT_REFRESH_TOKEN_EXPIRES_DAYS` — refresh-token TTL in days (default: `14`)

**Media uploads**
: `UPLOAD_FOLDER` — local upload path (default: `./uploads`)
: `MAX_CONTENT_LENGTH_MB` — max request body size in MB (default: `25`)

**CORS**
: `CORS_ORIGINS` — comma-separated list of allowed origins

**Scheduler**
: `SCHEDULER_ENABLED` — `true` / `false`
: `SCHEDULER_INTERVAL_SECONDS` — poll interval for scheduled publishes

**Bootstrap admin** (seed.py)
: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME`

See [`.env.example`](./.env.example) for a copy-pasteable template.

## URL Map

| Path | Purpose |
| --- | --- |
| `/` and `/news` | Public homepage (News18-style) |
| `/news/category/<slug>` | Category landing page |
| `/news/<slug>` | Public article detail |
| `/login` · `/logout` | CMS sign-in / sign-out |
| `/dashboard` | Newsroom dashboard (requires login) |
| `/posts` · `/posts/new` · `/posts/<id>/edit` | Article admin |
| `/alumni` · `/alumni/new` | Alumni directory admin |
| `/media` | Media library |
| `/users` | User admin (admin only) |
| `/api/*` | JWT-protected JSON API |
| `/api/health` | Liveness probe |

## Editorial Workflow

Posts flow through a state machine enforced by `app/utils/enums.py::ALLOWED_TRANSITIONS`:

```
draft  →  review  →  approved  →  ready_to_publish  →  published
  ↑         ↓           ↓                                  ↓
  └──── rejected        └──────── (back to draft)       archived
```

| Role | Can do |
| --- | --- |
| **writer** | Create/edit own drafts, submit for review, resubmit rejected posts |
| **editor** | Approve / reject / return to draft, mark ready-to-publish |
| **admin** | Publish, archive, override any transition, manage users |

Every save creates a `PostVersion` snapshot; scheduled publishes are driven by `SchedulerService` polling `publish_at`.

## JSON API

All endpoints are under `/api/` and return a consistent envelope:

```json
// Success
{
  "success": true,
  "data": { ... },
  "message": "Optional message",
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 0,
    "pages": 0,
    "has_next": false,
    "has_prev": false
  }
}

// Error
{
  "success": false,
  "message": "Not found",
  "details": null
}
```

Paginated list endpoints include a populated `meta` block; non-list responses omit it.

Authenticate once, reuse the access token:

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@dsvv.ac.in","password":"ChangeMe123!"}'

# Create a post
curl -X POST http://localhost:8000/api/posts \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Hello","content":"<p>World</p>","category":"news"}'
```

Main blueprints: `auth`, `posts`, `users`, `media`, `alumni`, `analytics`, `health`. See `app/routes/` for the full surface.

## Seed Data

`scripts/seed.py` ensures the app is usable on first boot:

1. Creates the three roles (`writer`, `editor`, `admin`).
2. Creates a bootstrap admin user.
3. Seeds **12 DSVV-themed demo posts** across all 6 categories so the News18-style homepage isn't empty.

Skip the demo posts with `SEED_DEMO_POSTS=false python scripts/seed.py`. Re-running the script is idempotent — it won't duplicate content.

## Development

**Run in dev mode**
```powershell
python run.py              # binds 0.0.0.0:8000 with debug reloader
```

**Sanity-check the app loads**
```powershell
python -c "from app import create_app; a = create_app(); print('OK', len(a.blueprints))"
```

**Compile-check all sources**
```powershell
python -m compileall -q app scripts
```

**Mongo ping**
```bash
mongosh --eval "db.adminCommand('ping')"
```

### Conventions

- **Models** (`app/models/*.py`) declare MongoEngine `Document`s with indexes in `meta = { ... }`.
- **Services** (`app/services/*.py`) hold business logic; controllers stay thin.
- **Routes** (`app/routes/*.py`) register blueprints and call controllers.
- **IDs** are ObjectId hex strings everywhere (URLs, JSON, JWT identity).
- **Workflow rules** live in one table: `ALLOWED_TRANSITIONS`.

## Deployment

```bash
gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
```

Production checklist:

- [ ] Set strong `SECRET_KEY` and `JWT_SECRET_KEY`
- [ ] Point `MONGODB_HOST` at a managed cluster (Atlas or self-hosted replica set)
- [ ] `SESSION_COOKIE_SECURE=true` and serve behind HTTPS
- [ ] Restrict `CORS_ORIGINS` to your real domains
- [ ] Put Nginx / a CDN in front for static + uploads
- [ ] Move `UPLOAD_FOLDER` to object storage (S3/GCS) or a persistent volume
- [ ] Set `FLASK_CONFIG=production`

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ServerSelectionTimeoutError` | MongoDB isn't running or `MONGODB_HOST` is wrong. Try `mongosh --eval "db.adminCommand('ping')"`. |
| `AttributeError: 'PostCategory' has no attribute 'values'` | Pull the latest code — `values()` classmethods were added to all enums. |
| Homepage shows no posts | Run `python scripts/seed.py` to create the 12 demo articles. |
| `CSRF token missing` on admin forms | Ensure the `base.html` form includes `{{ form.csrf_token }}` (or the hidden `csrf_token` input), and don't open the form in a second tab after the session expired. |
| JWT 401 on valid-looking request | Access token lifetime is 60 min by default. Hit `/api/auth/refresh` with the refresh token. |
| Can't publish a draft | Check `ALLOWED_TRANSITIONS` and your role — only admins can move `ready_to_publish → published`. |

## Acknowledgements

- **Dev Sanskriti Vishwavidyalaya** — subject matter and brand context
- **News18 India** — visual design inspiration for the public site
- **Flask**, **MongoEngine**, **APScheduler**, and **Marshmallow** communities — for the libraries that power this project

## License

Released under the **MIT License**.

---

<div align="center">

Built for <strong>Dev Sanskriti Vishwavidyalaya</strong> · Haridwar

</div>
