"""
Seed script.

Creates the three roles (writer/editor/admin), a bootstrap admin user, and
a set of sample published posts across all categories so the News18-style
public homepage has content out of the box.

Usage:
    python scripts/seed.py
Env:
    ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME (optional overrides)
    SEED_DEMO_POSTS=false to skip seeding demo posts
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make the app package importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.models.role import Role
from app.models.user import User
from app.models.post import Post
from app.models.tag import Tag
from app.utils.enums import RoleName, PostStatus, PostCategory
from app.utils.slug import generate_unique_slug


SAMPLE_POSTS = [
    {
        "title": "DSVV Celebrates 22nd Convocation, 2,340 Graduates Honoured at Shantikunj",
        "subtitle": "Governor of Uttarakhand presides over the day-long ceremony.",
        "category": PostCategory.NEWS.value,
        "excerpt": "The university conferred degrees across 87 programmes during a ceremony attended by dignitaries, faculty, parents and thousands of students.",
        "content": (
            "<p>Dev Sanskriti Vishwavidyalaya held its 22nd annual convocation at the Shantikunj campus on Saturday, "
            "conferring degrees and diplomas on 2,340 graduates across undergraduate, postgraduate and doctoral programmes.</p>"
            "<p>The chief guest, Governor of Uttarakhand, urged graduates to build careers rooted in service and cultural clarity. "
            "Vice-Chancellor Prof. Sharad Pardhy said the batch represented 26 Indian states and seven countries, reflecting the "
            "university\u2019s growing international footprint.</p>"
            "<h3>Gold medals and distinction</h3>"
            "<p>Forty-one students received gold medals for academic distinction, with the highest honours going to candidates from the "
            "schools of Yogic Science, Indian Culture, and Rural Management.</p>"
        ),
        "tags": ["convocation", "shantikunj", "graduation"],
        "is_featured": True,
        "is_pinned": False,
    },
    {
        "title": "Prof. Sharad Pardhy Appointed as New Vice-Chancellor for Second Term",
        "category": PostCategory.NEWS.value,
        "excerpt": "The governing council cites strong research output and campus reforms as reasons for continuity.",
        "content": (
            "<p>The governing council of Dev Sanskriti Vishwavidyalaya has appointed Prof. Sharad Pardhy to a second term as "
            "Vice-Chancellor, citing his record on research partnerships and campus modernisation.</p>"
            "<p>Prof. Pardhy outlined a four-year roadmap focused on digital pedagogy, interdisciplinary research, and alumni "
            "re-engagement.</p>"
        ),
        "tags": ["administration", "vice-chancellor"],
        "is_featured": False,
        "is_pinned": True,
    },
    {
        "title": "New MA in Applied Yogic Science Launched for 2025 Academic Session",
        "category": PostCategory.ACADEMICS.value,
        "excerpt": "The two-year programme blends classical pranayama with modern movement science and research methodology.",
        "content": (
            "<p>Dev Sanskriti Vishwavidyalaya will open admissions for a new MA in Applied Yogic Science from the 2025 academic session.</p>"
            "<p>The two-year residential programme pairs classical pranayama and asana practice with movement science, anatomy, and "
            "contemporary research methods. The first cohort is capped at 60 students.</p>"
            "<h3>Admission window</h3>"
            "<p>Applications open on 15 June and close on 20 July. Entrance is via written test and interview at the main campus.</p>"
        ),
        "tags": ["yoga", "admissions", "new-programme"],
    },
    {
        "title": "DSVV Student Wins National Scholarship for Sanskrit Manuscript Conservation",
        "category": PostCategory.ACADEMICS.value,
        "excerpt": "Priya Nair, MA Indian Culture, will spend a year at the National Mission for Manuscripts.",
        "content": (
            "<p>Priya Nair, a second-year MA student in the School of Indian Culture, has been awarded a national scholarship for "
            "manuscript conservation research.</p>"
            "<p>She will spend the coming year at the National Mission for Manuscripts in New Delhi, cataloguing palm-leaf texts from "
            "the Kerala tradition.</p>"
        ),
        "tags": ["scholarship", "sanskrit", "students"],
    },
    {
        "title": "Sanskar Utsav 2025: Cultural Fest Draws 40 Colleges to Haridwar Campus",
        "category": PostCategory.CULTURE.value,
        "excerpt": "Three days of classical dance, debate, and devotional music across four stages.",
        "content": (
            "<p>The annual cultural fest <em>Sanskar Utsav</em> returned to DSVV this week with 40 participating colleges and "
            "more than 180 events across four stages.</p>"
            "<p>Highlights included an inter-university Bharatanatyam recital, a national-level Sanskrit debate final, and a "
            "candle-lit <em>ganga aarti</em> performance on the riverbank.</p>"
        ),
        "tags": ["sanskar-utsav", "fest", "dance", "music"],
        "is_featured": False,
    },
    {
        "title": "International Yoga Day: 5,000 Practitioners Gather on the Ganga Ghats",
        "category": PostCategory.CULTURE.value,
        "excerpt": "Students, faculty and residents joined a dawn session on the ghats led by the Yogic Science department.",
        "content": (
            "<p>The university\u2019s Yogic Science department led a dawn practice on the Ganga ghats for the 11th International "
            "Yoga Day, drawing an estimated 5,000 participants.</p>"
            "<p>The session focused on sukshma vyayama and the full surya namaskar sequence, followed by a 20-minute guided "
            "pranayama.</p>"
        ),
        "tags": ["yoga", "ganga", "community"],
    },
    {
        "title": "End-Semester Examination Schedule Released for Summer 2025",
        "category": PostCategory.ANNOUNCEMENTS.value,
        "excerpt": "Written papers run 12\u201328 May. Hall tickets available on the student portal from 5 May.",
        "content": (
            "<p>The controller of examinations has released the end-semester schedule for Summer 2025.</p>"
            "<p>Written papers will be held from 12 to 28 May. Hall tickets will be available on the student portal from 5 May and "
            "must be carried to every sitting along with a valid ID.</p>"
        ),
        "tags": ["examinations", "schedule"],
        "is_announcement": True,
    },
    {
        "title": "Campus Closed on 14 April for Ambedkar Jayanti; Library Remains Open",
        "category": PostCategory.ANNOUNCEMENTS.value,
        "excerpt": "Administrative offices closed, but the central library and hostel mess continue as usual.",
        "content": (
            "<p>The campus will be closed on 14 April in observance of Ambedkar Jayanti.</p>"
            "<p>Administrative offices, the admissions cell, and the finance counter will remain shut. The central library, "
            "hostel mess, and medical centre will operate on normal timings.</p>"
        ),
        "tags": ["holiday", "notice"],
        "is_announcement": True,
    },
    {
        "title": "International Conference on Ayurveda and Longevity to Host 30 Countries",
        "category": PostCategory.EVENTS.value,
        "excerpt": "Three-day conference opens on 12 July with keynote from Dr. Vasant Lad.",
        "content": (
            "<p>The School of Ayurveda will host an international conference on <em>Ayurveda and Longevity</em> from 12 to 14 July, "
            "with delegates from 30 countries.</p>"
            "<p>The keynote will be delivered by Dr. Vasant Lad, founder of the Ayurvedic Institute, Albuquerque. Early-bird "
            "registration closes on 15 June.</p>"
        ),
        "tags": ["ayurveda", "conference", "international"],
    },
    {
        "title": "Annual Alumni Meet \u2018Sangam 2025\u2019 to Be Held at Shantikunj",
        "category": PostCategory.EVENTS.value,
        "excerpt": "Over 1,200 alumni expected; a career mentoring track will match 200 current students with industry professionals.",
        "content": (
            "<p>The annual alumni meet <em>Sangam 2025</em> will be held at the Shantikunj campus on 9 August, bringing "
            "together more than 1,200 graduates from the past two decades.</p>"
            "<p>A new career mentoring track will pair 200 current students with alumni professionals across media, healthcare, "
            "public policy, and the arts.</p>"
        ),
        "tags": ["alumni", "sangam", "networking"],
    },
    {
        "title": "DSVV Research Paper on Vedic Mathematics Accepted in Springer Journal",
        "category": PostCategory.RESEARCH.value,
        "excerpt": "Faculty-led study benchmarks sutra-based arithmetic against modern computational algorithms.",
        "content": (
            "<p>A research paper co-authored by faculty of the School of Science and Technology has been accepted in a "
            "peer-reviewed Springer journal.</p>"
            "<p>The study benchmarks 14 sutras of Vedic mathematics against modern computational algorithms and documents "
            "measurable gains on specific classes of multiplication problems.</p>"
        ),
        "tags": ["research", "vedic-math", "publication"],
    },
    {
        "title": "ICSSR Grant of \u20b948 Lakh Awarded to DSVV for Yoga-in-Schools Study",
        "category": PostCategory.RESEARCH.value,
        "excerpt": "Two-year project will measure the impact of structured yoga on adolescent attention and stress markers.",
        "content": (
            "<p>The Indian Council of Social Science Research has awarded a \u20b948 lakh grant to DSVV for a two-year study on "
            "yoga in secondary schools.</p>"
            "<p>The project will run across 60 schools in three states and measure changes in attention, stress markers and "
            "self-reported well-being using pre-post instruments.</p>"
        ),
        "tags": ["icssr", "grant", "yoga-research"],
    },
]


def _seed_roles():
    for role_name in RoleName.values():
        if not Role.objects(name=role_name).first():
            Role(name=role_name, description=f"{role_name.title()} role").save()
    print("[seed] Roles ready:", RoleName.values())


def _seed_admin() -> User:
    email = os.getenv("ADMIN_EMAIL", "admin@dsvv.ac.in")
    password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    name = os.getenv("ADMIN_NAME", "DSVV Admin")

    admin = User.objects(email=email).first()
    if admin:
        print(f"[seed] Admin already exists: {email}")
        return admin

    admin = User(name=name, email=email)
    admin.set_password(password)
    admin_role = Role.objects(name=RoleName.ADMIN.value).first()
    if admin_role:
        admin.roles.append(admin_role)
    admin.save()
    print(f"[seed] Admin created: {email} / {password}")
    return admin


def _seed_demo_posts(author: User):
    if os.getenv("SEED_DEMO_POSTS", "true").lower() == "false":
        print("[seed] Skipping demo posts (SEED_DEMO_POSTS=false).")
        return

    existing = Post.objects.count()
    if existing > 0:
        print(f"[seed] Skipping demo posts ({existing} post(s) already exist).")
        return

    now = datetime.utcnow()
    created = 0
    for idx, spec in enumerate(SAMPLE_POSTS):
        # Space out published_at so ordering looks natural.
        published_at = now - timedelta(hours=idx * 9)

        tag_names = spec.pop("tags", [])
        tags = [Tag.get_or_create(t) for t in tag_names]

        post = Post(
            title=spec["title"],
            subtitle=spec.get("subtitle"),
            slug=generate_unique_slug(spec["title"], Post),
            excerpt=spec.get("excerpt"),
            content=spec["content"],
            category=spec["category"],
            status=PostStatus.PUBLISHED.value,
            is_featured=spec.get("is_featured", False),
            is_pinned=spec.get("is_pinned", False),
            is_announcement=spec.get("is_announcement", False),
            published_at=published_at,
            publish_at=published_at,
            author=author,
            tags=tags,
        )
        post.save()
        created += 1

    print(f"[seed] Created {created} demo post(s) across {len(PostCategory)} categories.")


def seed():
    app = create_app()
    with app.app_context():
        _seed_roles()
        admin = _seed_admin()
        _seed_demo_posts(admin)


if __name__ == "__main__":
    seed()
