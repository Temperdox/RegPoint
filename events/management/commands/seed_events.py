"""Idempotently seed demo events that never expire.

Safe to run on every deploy: events are keyed by slug via get_or_create,
and seeded events always have expires_at=None so they never drop off the
public list.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Event, EventCategory, TicketType


class Command(BaseCommand):
    help = "Seed the database with demo events that never expire"

    def handle(self, *args, **options):
        categories_by_slug = {}
        for name, slug in [
            ("Conference", "conference"),
            ("Workshop", "workshop"),
            ("Webinar", "webinar"),
            ("Networking", "networking"),
            ("Product Launch", "product-launch"),
        ]:
            cat, _ = EventCategory.objects.get_or_create(
                slug=slug, defaults={"name": name}
            )
            categories_by_slug[slug] = cat

        organizer = (
            User.objects.filter(is_superuser=True).order_by("pk").first()
            or User.objects.filter(is_staff=True).order_by("pk").first()
            or User.objects.order_by("pk").first()
        )
        if organizer is None:
            organizer, _ = User.objects.get_or_create(
                username="demo-organizer",
                defaults={
                    "email": "organizer@nexbridge.example.com",
                    "first_name": "Demo",
                    "last_name": "Organizer",
                },
            )

        now = timezone.now()
        events_data = [
            {
                "title": "Digital Marketing Summit 2026",
                "slug": "digital-marketing-summit-2026",
                "description": (
                    "Join industry leaders for a full-day summit on the "
                    "latest digital marketing trends, AI-driven campaigns, "
                    "and data analytics strategies. Featuring keynote "
                    "speakers from Fortune 500 companies."
                ),
                "category": categories_by_slug["conference"],
                "date": now + timedelta(days=30),
                "end_date": now + timedelta(days=30, hours=8),
                "location": "Nexbridge Convention Center, New York, NY",
                "capacity": 500,
                "price": 199.00,
            },
            {
                "title": "SEO Mastery Workshop",
                "slug": "seo-mastery-workshop",
                "description": (
                    "Hands-on workshop covering advanced SEO techniques, "
                    "keyword research, technical SEO audits, and link "
                    "building strategies for 2026."
                ),
                "category": categories_by_slug["workshop"],
                "date": now + timedelta(days=14),
                "end_date": now + timedelta(days=14, hours=4),
                "location": "Nexbridge Training Lab, Austin, TX",
                "capacity": 50,
                "price": 79.00,
            },
            {
                "title": "Social Media Analytics Webinar",
                "slug": "social-media-analytics-webinar",
                "description": (
                    "Free webinar exploring the latest social media "
                    "analytics tools and how to measure ROI on your "
                    "social campaigns effectively."
                ),
                "category": categories_by_slug["webinar"],
                "date": now + timedelta(days=7),
                "end_date": now + timedelta(days=7, hours=2),
                "location": "Online (Zoom)",
                "capacity": 1000,
                "price": 0.00,
            },
            {
                "title": "CMO Networking Mixer",
                "slug": "cmo-networking-mixer",
                "description": (
                    "An exclusive evening networking event for Chief "
                    "Marketing Officers and senior marketing leaders. "
                    "Cocktails, conversation, and connections."
                ),
                "category": categories_by_slug["networking"],
                "date": now + timedelta(days=21),
                "end_date": now + timedelta(days=21, hours=3),
                "location": "The Rooftop Lounge, Chicago, IL",
                "capacity": 100,
                "price": 49.00,
            },
            {
                "title": "Nexbridge Product Launch: AdPulse 3.0",
                "slug": "nexbridge-adpulse-launch",
                "description": (
                    "Be the first to see Nexbridge's next-generation ad "
                    "platform. Live demos, Q&A with the product team, "
                    "and early access registration."
                ),
                "category": categories_by_slug["product-launch"],
                "date": now + timedelta(days=45),
                "end_date": now + timedelta(days=45, hours=3),
                "location": "Nexbridge HQ, San Francisco, CA",
                "capacity": 200,
                "price": 0.00,
            },
            {
                "title": "Content Strategy Bootcamp",
                "slug": "content-strategy-bootcamp",
                "description": (
                    "A two-day intensive bootcamp on building and "
                    "executing content strategies that drive leads. "
                    "Includes hands-on exercises and real case studies."
                ),
                "category": categories_by_slug["workshop"],
                "date": now + timedelta(days=60),
                "end_date": now + timedelta(days=61),
                "location": "Nexbridge Training Center, Boston, MA",
                "capacity": 40,
                "price": 299.00,
            },
        ]

        created_count = 0
        for data in events_data:
            defaults = {
                **data,
                "created_by": organizer,
                "is_active": True,
                "expires_at": None,
            }
            event, created = Event.objects.get_or_create(
                slug=data["slug"], defaults=defaults
            )
            if created:
                created_count += 1
                TicketType.objects.create(
                    event=event,
                    name="General Admission",
                    price=data["price"],
                    quantity_available=int(data["capacity"] * 0.7),
                )
                if data["price"] > 0:
                    TicketType.objects.create(
                        event=event,
                        name="VIP",
                        price=round(float(data["price"]) * 2, 2),
                        quantity_available=int(data["capacity"] * 0.3),
                    )
                self.stdout.write(f"  + {event.title}")
            else:
                self.stdout.write(f"  . {event.title} (already exists)")

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_events complete: {created_count} new, "
                f"{len(events_data) - created_count} already present."
            )
        )
