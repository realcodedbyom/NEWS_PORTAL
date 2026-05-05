"""
Scrape latest news from https://www.awgp.org/en/news and import them as
published posts into the local DB. Images are mirrored to Cloudinary so
the app owns durable copies.

Usage:
    python scripts/scrape_awgp.py                 # 50 latest, wipes existing posts/media
    python scripts/scrape_awgp.py --limit 20      # fewer articles
    python scripts/scrape_awgp.py --no-wipe       # keep existing posts
    python scripts/scrape_awgp.py --category news --category research

Env:
    ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME   (admin bootstrap)

Notes:
    The listing page exposes thumbnails + article IDs. Pagination is
    an AJAX POST to /api/gurukulam/post/getNewsHtml. Each article
    detail page (/en/news?id=<N>) has the title in <h3> and the body
    in <div class="contentView editable">. Content is often in Hindi.
"""
from __future__ import annotations

import argparse
import io
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bleach
import requests
from bs4 import BeautifulSoup
from flask import current_app

# Make the app package importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cloudinary.uploader  # noqa: E402  (must come after sys.path tweak)

# Ensure stdout/stderr can carry Devanagari / other non-ASCII text on
# Windows consoles (default code page is cp1252, which can't encode Hindi).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


def _safe_print(msg: str) -> None:
    """Print that never crashes on encoding errors (Windows + Devanagari)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)

from app import create_app  # noqa: E402
from app.models.media import Media  # noqa: E402
from app.models.post import Post, PostVersion  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.tag import Tag  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.enums import MediaType, PostCategory, PostStatus, RoleName  # noqa: E402
from app.utils.slug import generate_unique_slug  # noqa: E402


BASE_URL = "https://www.awgp.org"
LIST_URL = f"{BASE_URL}/en/news"
AJAX_URL = f"{BASE_URL}/api/gurukulam/post/getNewsHtml"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DEFAULT_LIMIT = 50
PAGE_SIZE = 10  # server-side totalRows
REQUEST_DELAY_SEC = 0.3
REQUEST_TIMEOUT_SEC = 20
MAX_RETRIES = 3

# HTML sanitization: awgp.org is third-party content, so we strip any
# <script>, on* handlers, iframes, etc. before storing in Post.content
# (which is rendered with |safe in the public detail template).
SAFE_TAGS = {
    "p", "br", "span", "div", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "em", "b", "i", "u", "small", "sub", "sup",
    "a", "img",
    "blockquote", "pre", "code",
    "figure", "figcaption",
    "table", "thead", "tbody", "tr", "td", "th",
}
SAFE_ATTRS = {
    "*": ["class", "id"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
}
SAFE_PROTOCOLS = ["http", "https", "mailto"]

# Awgp.org-specific UI junk that lives INSIDE the same container as the
# real article text. bleach.clean(strip=True) removes the tag but keeps
# its inner text, so <style>…</style> + <script>…</script> would leak as
# visible plaintext. We decompose these via BeautifulSoup *before* bleach
# runs so both the tag and its contents are gone.
AWGP_JUNK_IDS = frozenset({
    "sharePage", "image-popup", "updateName", "PopulateNext",
    "baseView", "popup-img", "mainImage",
})
AWGP_JUNK_CLASSES = frozenset({
    "popup", "popup-content", "close", "image-container",
    "newsView1", "banner-area", "overlay", "overlay-bg",
    "topBarAddWord", "share-list", "topBar",
    "single-destination-sidebar", "menu-has-children",
    "social-icon", "footer-area", "breadcrumb",
})
AWGP_NOISE_TEXT = frozenset({
    "sharePage", "Get More", "Read More", "\u00d7", "×",
    "Login", "Share",
})
# Short section headers that introduce awgp's duplicate gallery /
# "related news" blocks. Note "phots" — awgp's own misspelling.
AWGP_SECTION_HEADERS = frozenset({
    "phots", "photos", "photo", "image", "images",
    "videos", "video", "more news", "related news",
    "more posts", "related posts",
})
AWGP_STRIP_TAGS = (
    "script", "style", "noscript", "iframe", "form",
    "button", "input", "select", "textarea",
    "nav", "header", "footer", "link", "meta",
)
# A <div>…</div> whose entire text matches one of these is treated as a
# date-only line (duplicates our stored published_at) and removed.
_DATE_LINE_RE = re.compile(
    r"^[\s\u00A0]*(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Jan|Feb|Mar|Apr|"
    r"Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2}[,\s].{0,60}$",
    re.I,
)


def _sanitize_html(html: str) -> str:
    """Strip <script>, on* handlers, and other unsafe constructs."""
    return bleach.clean(
        html,
        tags=SAFE_TAGS,
        attributes=SAFE_ATTRS,
        protocols=SAFE_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


@dataclass
class ScrapedArticle:
    """Parsed article ready for import."""
    article_id: str
    url: str
    title: str
    body_html: str
    plain_text: str
    published_at: datetime | None
    thumbnail_url: str | None
    image_urls: list[str] = field(default_factory=list)


class AwgpScraper:
    """Fetch + parse articles from awgp.org. No DB access."""

    def __init__(self, *, delay: float = REQUEST_DELAY_SEC, verbose: bool = True):
        self.delay = delay
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        })
        self._csrf_token: str | None = None

    # ---- low-level HTTP ----

    def _log(self, msg: str) -> None:
        if self.verbose:
            _safe_print(msg)

    def _get(self, url: str, **kwargs) -> requests.Response:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", REQUEST_TIMEOUT_SEC)
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                if self.delay:
                    time.sleep(self.delay + random.uniform(0, 0.15))
                return resp
            except (requests.RequestException, requests.HTTPError) as exc:
                last_exc = exc
                backoff = 0.5 * (2 ** (attempt - 1))
                self._log(f"  [retry {attempt}/{MAX_RETRIES}] {method} {url} failed: {exc} (sleeping {backoff}s)")
                time.sleep(backoff)
        raise RuntimeError(f"{method} {url} failed after {MAX_RETRIES} attempts: {last_exc}")

    # ---- listing / pagination ----

    def bootstrap(self) -> None:
        """Fetch the landing page to seed session cookie + CSRF token."""
        self._log(f"[scrape] GET {LIST_URL}")
        resp = self._get(LIST_URL)
        html = resp.text
        m = re.search(r'csrf_token\s*=\s*["\']([^"\']+)["\']', html)
        if not m:
            # Fallback: look for a meta/hidden input
            m = re.search(r'name=["\']csrfmiddlewaretoken["\'][^>]*value=["\']([^"\']+)', html)
        if not m:
            raise RuntimeError("Could not locate csrf_token on listing page")
        self._csrf_token = m.group(1)
        self._log(f"[scrape] csrf_token acquired ({len(self._csrf_token)} chars)")

        # Also capture the first page of IDs directly from the landing HTML,
        # since the inline render is cheaper than an extra AJAX round-trip.
        self._initial_html = html

    def _parse_ids_from_html(self, html: str) -> list[tuple[str, str | None]]:
        """Return list of (article_id, thumbnail_url) tuples in page order."""
        soup = BeautifulSoup(html, "html.parser")
        pairs: list[tuple[str, str | None]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            m = re.search(r"/en/news\?id=(\d+)", a["href"])
            if not m:
                continue
            aid = m.group(1)
            if aid in seen:
                continue
            seen.add(aid)
            img = a.find("img")
            thumb = None
            if img:
                thumb = img.get("src") or img.get("data-src")
                if thumb and thumb.startswith("//"):
                    thumb = "https:" + thumb
                elif thumb and thumb.startswith("/"):
                    thumb = BASE_URL + thumb
            pairs.append((aid, thumb))
        return pairs

    def collect_article_ids(self, limit: int) -> list[tuple[str, str | None]]:
        """Walk the listing (landing HTML + AJAX pages) until we have `limit` ids."""
        if self._csrf_token is None:
            self.bootstrap()

        collected: list[tuple[str, str | None]] = []
        seen: set[str] = set()

        def extend(batch: list[tuple[str, str | None]]) -> None:
            for aid, thumb in batch:
                if aid not in seen:
                    seen.add(aid)
                    collected.append((aid, thumb))

        # Page 0 comes from the inline landing HTML.
        extend(self._parse_ids_from_html(self._initial_html))
        self._log(f"[scrape] landing page yielded {len(collected)} ids")

        offset = len(collected)
        empty_pages = 0
        while len(collected) < limit and empty_pages < 2:
            headers = {
                "Referer": LIST_URL,
                "Origin": BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = {
                "csrfmiddlewaretoken": self._csrf_token,
                "from": str(offset),
                "totalRows": str(PAGE_SIZE),
            }
            try:
                resp = self._post(AJAX_URL, headers=headers, data=data)
            except RuntimeError as exc:
                self._log(f"[scrape] pagination stopped: {exc}")
                break

            body = resp.text.strip()
            if not body or len(body) < 20:
                empty_pages += 1
                offset += PAGE_SIZE
                continue

            # The response may be raw HTML or JSON-wrapped.
            html_fragment = body
            if body.startswith("{") or body.startswith("["):
                try:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        html_fragment = (
                            payload.get("html")
                            or payload.get("data")
                            or payload.get("content")
                            or ""
                        )
                    elif isinstance(payload, list):
                        html_fragment = "".join(str(x) for x in payload)
                except ValueError:
                    html_fragment = body

            before = len(collected)
            extend(self._parse_ids_from_html(html_fragment))
            gained = len(collected) - before
            self._log(f"[scrape] offset={offset} +{gained} ids (total {len(collected)})")
            if gained == 0:
                empty_pages += 1
            else:
                empty_pages = 0
            offset += PAGE_SIZE

        return collected[:limit]

    # ---- detail page ----

    _MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
        "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }

    def _parse_date(self, text: str) -> datetime | None:
        # Match "April 25, 2026" or "Apr 25, 2026" patterns.
        m = re.search(
            r"\b(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
            text, re.IGNORECASE,
        )
        if m:
            month = self._MONTHS[m.group(1).lower()]
            try:
                return datetime(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                return None
        # dd/mm/yyyy or dd-mm-yyyy
        m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None
        return None

    def _clean_body(self, body_el) -> None:
        """Strip awgp.org-specific UI junk from ``body_el`` in-place.

        The scraped container mixes real article text with the site's
        navigation, share widget, image popup, inline <style>/<script>,
        and a "Phots" gallery section. This method removes every known
        non-article element so the remaining HTML is safe to sanitize
        and render.
        """
        from bs4 import NavigableString  # local import: keeps top-level tidy

        # 1. Decompose dangerous/unwanted tags entirely (tag + its text).
        for tag_name in AWGP_STRIP_TAGS:
            for tag in body_el.find_all(tag_name):
                tag.decompose()

        # 2. Remove elements with a known awgp UI id.
        for junk_id in AWGP_JUNK_IDS:
            for el in body_el.find_all(id=junk_id):
                el.decompose()

        # 3. Remove elements whose class list intersects the junk set.
        #    Snapshot the list first and skip elements that have been
        #    detached (their parent was decomposed earlier in the same
        #    pass, so bs4 has nulled their internal refs).
        for el in list(body_el.find_all(True)):
            if el is None or not hasattr(el, "get") or el.parent is None:
                continue
            classes = el.get("class") or []
            if classes and set(classes) & AWGP_JUNK_CLASSES:
                el.decompose()

        # 4. Strip inline event handlers + style attrs from everything
        #    that's still attached to the tree.
        for el in list(body_el.find_all(True)):
            if el is None or not hasattr(el, "attrs") or el.parent is None:
                continue
            for attr in list(el.attrs):
                if attr.startswith("on") or attr == "style":
                    del el.attrs[attr]

        # 5. Drop section headers for awgp's photo/related blocks
        #    (including their "Phots" misspelling).
        for h in list(body_el.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])):
            if h is None or h.parent is None:
                continue
            if h.get_text(strip=True).lower() in AWGP_SECTION_HEADERS:
                h.decompose()

        # 6. Drop "Read More" / "Get More" anchors, javascript: links,
        #    and cross-article links back to awgp; unwrap other internal
        #    anchors so their text survives but the broken href dies.
        for a in list(body_el.find_all("a", href=True)):
            if a is None or a.parent is None:
                continue
            href = (a.get("href") or "").strip()
            txt = a.get_text(strip=True).lower()
            if txt in {"read more", "get more", "more", "login", "read"}:
                a.decompose()
                continue
            if (
                href.startswith("javascript:")
                or href.startswith("#")
                or "/en/news?id=" in href
                or "/en/blog?id=" in href
            ):
                a.decompose()
                continue
            if href.startswith("/") or "awgp.org" in href:
                a.unwrap()

        # 7. Extract stray noise text nodes ("×", "sharePage", …).
        for txt in list(body_el.find_all(string=True)):
            if txt is None:
                continue
            if isinstance(txt, NavigableString) and str(txt).strip() in AWGP_NOISE_TEXT:
                try:
                    txt.extract()
                except Exception:
                    pass

        # 8. Remove short <div>s that are just a date line — duplicates
        #    what we already render via post.published_at.
        for div in list(body_el.find_all("div")):
            if div is None or div.parent is None:
                continue
            txt = div.get_text(strip=True)
            if txt and len(txt) <= 80 and _DATE_LINE_RE.match(txt):
                div.decompose()

        # 9. Collapse now-empty wrappers. Repeat until stable so deeply
        #    nested empty chains all collapse in one cleanup pass.
        for _ in range(3):
            removed = 0
            for el in list(body_el.find_all(["div", "span", "section", "article", "aside"])):
                if el is None or el.parent is None:
                    continue
                if not el.get_text(strip=True) and not el.find(["img", "video", "audio", "figure", "br"]):
                    el.decompose()
                    removed += 1
            if removed == 0:
                break

    def fetch_article(self, article_id: str, thumbnail: str | None = None) -> ScrapedArticle | None:
        url = f"{LIST_URL}?id={article_id}"
        try:
            resp = self._get(url, headers={"Referer": LIST_URL})
        except RuntimeError as exc:
            self._log(f"  [skip] {article_id}: {exc}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Prefer the tighter .articleText scope; fall back to the outer
        # contentView / editable container if awgp changes its markup.
        body_el = (
            soup.find("div", class_=re.compile(r"\barticleText\b"))
            or soup.find("div", class_=re.compile(r"\bcontentView\b"))
            or soup.find("div", class_=re.compile(r"\beditable\b"))
        )
        if body_el is None:
            self._log(f"  [skip] {article_id}: no content container found")
            return None

        # Snapshot plain text + collect image URLs BEFORE cleanup wipes
        # them. Images go into post.gallery; plain_text feeds the date
        # parser + the excerpt.
        pre_clean_text = body_el.get_text(" ", strip=True)
        published_at = self._parse_date(pre_clean_text[:800])

        image_urls: list[str] = []
        seen_imgs: set[str] = set()
        for img in body_el.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = BASE_URL + src
            if not src.startswith("http"):
                continue
            # Skip obvious logos / UI chrome — we only want article photos.
            lower = src.lower()
            if "/logo" in lower or lower.endswith(".svg") or "/banner" in lower:
                continue
            if src in seen_imgs:
                continue
            seen_imgs.add(src)
            image_urls.append(src)

        # Aggressive cleanup — removes scripts/styles/popups/"Phots"/etc.
        self._clean_body(body_el)

        # Strip any remaining <img> tags so the body is pure text. The
        # images live in post.gallery and are rendered as a dedicated
        # grid below the article (cleaner than inline cascading).
        for img in body_el.find_all("img"):
            img.decompose()

        # Extract title from the first remaining heading (awgp's "Phots"
        # h3 was removed in _clean_body, so this lands on the real one).
        title_el = body_el.find(["h1", "h2", "h3"])
        if title_el is not None:
            title = title_el.get_text(strip=True)
            title_el.decompose()  # don't duplicate in body
        else:
            title = ""
        if not title:
            page_title = soup.find("title")
            title = (page_title.get_text(strip=True) if page_title else "").split("|")[0].strip()
        if not title:
            self._log(f"  [skip] {article_id}: no title")
            return None
        title = title[:250]

        # One more empty-wrapper pass now that the title+date are gone.
        for el in list(body_el.find_all(["div", "span", "section"])):
            if not el.get_text(strip=True) and not el.find(["img", "video", "audio", "figure", "br"]):
                el.decompose()

        plain_text = body_el.get_text(" ", strip=True)
        body_html = str(body_el)

        return ScrapedArticle(
            article_id=article_id,
            url=url,
            title=title,
            body_html=body_html,
            plain_text=plain_text,
            published_at=published_at,
            thumbnail_url=thumbnail,
            image_urls=image_urls,
        )


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


# Keywords → category mapping. First match wins; default is NEWS.
CATEGORY_KEYWORDS = [
    (PostCategory.EVENTS.value, (
        "event", "conference", "sammelan", "shivir", "samaroh", "utsav",
        "celebration", "festival", "workshop", "seminar",
    )),
    (PostCategory.RESEARCH.value, (
        "research", "study", "journal", "publication", "findings",
        "anusandhan", "vigyan",
    )),
    (PostCategory.ACADEMICS.value, (
        "student", "admission", "exam", "degree", "scholarship",
        "academic", "course", "curriculum", "vidyarthi",
    )),
    (PostCategory.CULTURE.value, (
        "yoga", "sanskriti", "culture", "music", "dance", "spiritual",
        "pragya", "sadhana", "meditation", "dharma",
    )),
    (PostCategory.ANNOUNCEMENTS.value, (
        "announcement", "notice", "notification", "holiday", "closed",
        "suchana",
    )),
]


def _infer_category(title: str, body_text: str) -> str:
    haystack = f"{title} {body_text[:800]}".lower()
    for cat, kws in CATEGORY_KEYWORDS:
        if any(kw in haystack for kw in kws):
            return cat
    return PostCategory.NEWS.value


def _make_excerpt(plain_text: str, limit: int = 280) -> str:
    t = re.sub(r"\s+", " ", plain_text).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0]
    return cut + "…"


class AwgpImporter:
    """Persist ScrapedArticle instances into the DB + Cloudinary."""

    def __init__(
        self,
        author: User,
        *,
        session: requests.Session | None = None,
        verbose: bool = True,
        cloudinary_folder: str | None = None,
    ):
        self.author = author
        self.verbose = verbose
        # Resolve the Cloudinary folder from config so we stay consistent
        # with MediaService.upload (uses CLOUDINARY_UPLOAD_FOLDER).
        if cloudinary_folder is None:
            base = current_app.config.get("CLOUDINARY_UPLOAD_FOLDER", "dsvv_news")
            cloudinary_folder = f"{base}/awgp"
        self.cloudinary_folder = cloudinary_folder
        # Reuse the scraper's authenticated session so we inherit cookies
        # and can spoof Referer/User-Agent on image downloads.
        self.session = session or requests.Session()
        if session is None:
            self.session.headers.update({"User-Agent": USER_AGENT})
        self._uploaded_cache: dict[str, Media] = {}  # remote URL → Media
        self._failed_cache: set[str] = set()         # URLs we've already failed on

    def _log(self, msg: str) -> None:
        if self.verbose:
            _safe_print(msg)

    # ---- wipe ----

    def wipe_existing(self) -> None:
        """Delete all Posts, PostVersions, and provider=cloudinary Media rows.

        Cloudinary assets are best-effort deleted; any failure is logged
        but does not abort the import.
        """
        post_count = Post.objects.count()
        version_count = PostVersion.objects.count()
        media_count = Media.objects.count()
        self._log(f"[wipe] removing {post_count} post(s), {version_count} version(s), {media_count} media row(s)")

        for m in Media.objects:
            if m.provider == "cloudinary" and m.public_id:
                resource_type = "video" if m.media_type == MediaType.VIDEO.value else "image"
                try:
                    cloudinary.uploader.destroy(
                        m.public_id, resource_type=resource_type, invalidate=True,
                    )
                except Exception as exc:
                    self._log(f"  [warn] cloudinary destroy failed for {m.public_id}: {exc}")

        PostVersion.objects.delete()
        Post.objects.delete()
        Media.objects.delete()
        self._log("[wipe] done")

    # ---- cloudinary ----

    def _upload_remote_image(self, remote_url: str) -> Media | None:
        """Download image bytes ourselves, then upload to Cloudinary.

        awgp.org applies hotlink protection, so Cloudinary's server-side
        remote-fetch (passing a URL to cloudinary.uploader.upload) gets
        403 Forbidden. Downloading via our authenticated session with a
        proper Referer/User-Agent works — we then stream the bytes to
        Cloudinary directly.
        """
        if remote_url in self._uploaded_cache:
            return self._uploaded_cache[remote_url]
        if remote_url in self._failed_cache:
            return None

        # 1. Fetch bytes ourselves.
        try:
            resp = self.session.get(
                remote_url,
                headers={
                    "Referer": LIST_URL,
                    "User-Agent": USER_AGENT,
                },
                timeout=REQUEST_TIMEOUT_SEC,
            )
        except requests.RequestException as exc:
            self._log(f"  [warn] image download failed for {remote_url}: {exc}")
            self._failed_cache.add(remote_url)
            return None
        if resp.status_code != 200 or not resp.content:
            self._log(
                f"  [warn] image download non-200 ({resp.status_code}) for {remote_url}"
            )
            self._failed_cache.add(remote_url)
            return None
        data = resp.content
        mime_type = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()

        # 2. Upload bytes to Cloudinary.
        try:
            result = cloudinary.uploader.upload(
                io.BytesIO(data),
                folder=self.cloudinary_folder,
                resource_type="image",
                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
        except Exception as exc:
            self._log(f"  [warn] cloudinary upload failed for {remote_url}: {exc}")
            self._failed_cache.add(remote_url)
            return None

        public_id = result.get("public_id")
        secure_url = result.get("secure_url") or result.get("url")
        fmt = result.get("format") or "jpg"
        size_bytes = int(result.get("bytes") or len(data))
        width = result.get("width")
        height = result.get("height")

        if not secure_url:
            return None

        base = public_id.split("/")[-1] if public_id else "image"
        original_name = remote_url.rsplit("/", 1)[-1][:200] or f"{base}.{fmt}"

        media = Media(
            filename=f"{base}.{fmt}",
            original_name=original_name,
            url=secure_url,
            mime_type=mime_type or f"image/{fmt}",
            size_bytes=size_bytes,
            media_type=MediaType.IMAGE.value,
            width=width,
            height=height,
            provider="cloudinary",
            public_id=public_id,
            folder=self.cloudinary_folder,
            uploaded_by=self.author,
        )
        media.save()
        self._uploaded_cache[remote_url] = media
        return media

    # ---- per-article import ----

    # Upper bound on images we keep per article. Awgp occasionally has
    # 30+ gallery photos which bloats the DB + Cloudinary without adding
    # reader value.
    GALLERY_MAX = 20

    def import_article(self, art: ScrapedArticle, fallback_published_at: datetime) -> Post | None:
        # Skip exact title duplicates so re-runs stay idempotent (--no-wipe).
        if Post.objects(title=art.title).first():
            self._log(f"  [skip-dupe] {art.title[:60]}")
            return None

        # Body is already image-free (scraper stripped <img> tags). Still
        # run it through bleach as a defence-in-depth XSS gate.
        body_html = _sanitize_html(art.body_html)

        # Mirror each image URL to Cloudinary and build the gallery list.
        # Preserves source order so the first (main) image becomes featured.
        gallery: list[Media] = []
        seen_media_ids: set[str] = set()
        for remote_url in art.image_urls[: self.GALLERY_MAX * 2]:
            media = self._upload_remote_image(remote_url)
            if media is None:
                continue
            mid = str(media.id)
            if mid in seen_media_ids:
                continue
            seen_media_ids.add(mid)
            gallery.append(media)
            if len(gallery) >= self.GALLERY_MAX:
                break

        featured: Media | None = gallery[0] if gallery else None

        # Build post fields.
        published_at = art.published_at or fallback_published_at
        category = _infer_category(art.title, art.plain_text)
        excerpt = _make_excerpt(art.plain_text)
        slug = generate_unique_slug(art.title, Post)

        # Tags: category tag + source tag.
        tag_names = [category, "awgp"]
        tags = [Tag.get_or_create(t) for t in tag_names]

        post = Post(
            title=art.title,
            slug=slug,
            excerpt=excerpt,
            content=body_html,
            category=category,
            status=PostStatus.PUBLISHED.value,
            published_at=published_at,
            publish_at=published_at,
            author=self.author,
            publisher=self.author,
            featured_image=featured,
            gallery=gallery,
            tags=tags,
        )
        post.save()
        self._log(f"  [ok] {art.article_id}  {art.title[:70]}  ({len(gallery)} img, cat={category})")
        return post


# ---------------------------------------------------------------------------
# Admin bootstrap (shared with seed.py)
# ---------------------------------------------------------------------------


def ensure_roles_and_admin() -> User:
    for role_name in RoleName.values():
        if not Role.objects(name=role_name).first():
            Role(name=role_name, description=f"{role_name.title()} role").save()

    email = os.getenv("ADMIN_EMAIL", "admin@dsvv.ac.in")
    password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    name = os.getenv("ADMIN_NAME", "DSVV Admin")

    admin = User.objects(email=email).first()
    if admin:
        return admin

    admin = User(name=name, email=email)
    admin.set_password(password)
    admin_role = Role.objects(name=RoleName.ADMIN.value).first()
    if admin_role:
        admin.roles.append(admin_role)
    admin.save()
    _safe_print(f"[seed] Admin created: {email} / {password}")
    return admin


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_scrape(
    *,
    limit: int = DEFAULT_LIMIT,
    wipe: bool = True,
    verbose: bool = True,
) -> dict:
    """End-to-end: scrape awgp.org, import into DB, return summary dict.

    Must be called inside a Flask app context (caller's responsibility).
    """
    admin = ensure_roles_and_admin()

    scraper = AwgpScraper(verbose=verbose)
    scraper.bootstrap()

    pairs = scraper.collect_article_ids(limit)
    if not pairs:
        _safe_print("[scrape] no article IDs found — aborting.")
        return {"imported": 0, "skipped": 0, "attempted": 0}

    _safe_print(f"[scrape] collected {len(pairs)} article id(s); fetching details…")

    importer = AwgpImporter(admin, session=scraper.session, verbose=verbose)
    if wipe:
        importer.wipe_existing()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    imported = 0
    skipped = 0
    for idx, (aid, thumb) in enumerate(pairs):
        art = scraper.fetch_article(aid, thumbnail=thumb)
        if art is None:
            skipped += 1
            continue
        # Space out fallback published_at so the homepage ordering looks natural.
        fallback = now - timedelta(hours=idx * 6)
        try:
            post = importer.import_article(art, fallback_published_at=fallback)
        except Exception as exc:
            _safe_print(f"  [error] {aid}: {exc}")
            skipped += 1
            continue
        if post is None:
            skipped += 1
        else:
            imported += 1

    summary = {"imported": imported, "skipped": skipped, "attempted": len(pairs)}
    _safe_print(f"[scrape] done. imported={imported} skipped={skipped} attempted={len(pairs)}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape awgp.org/en/news into the DB.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Max articles to import (default {DEFAULT_LIMIT})")
    parser.add_argument("--no-wipe", dest="wipe", action="store_false",
                        help="Do NOT delete existing posts/media before import.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-item logs.")
    parser.set_defaults(wipe=True)
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        summary = run_scrape(
            limit=args.limit,
            wipe=args.wipe,
            verbose=not args.quiet,
        )
    return 0 if summary.get("imported", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
