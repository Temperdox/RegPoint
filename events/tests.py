from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import Event, EventCategory, Registration, TicketType


class HomePageTest(TestCase):
    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RegPoint")


class EventListTest(TestCase):
    def test_event_list_loads(self):
        response = self.client.get("/events/")
        self.assertEqual(response.status_code, 200)


class AuthTest(TestCase):
    def test_signup_page_loads(self):
        response = self.client.get("/signup/")
        self.assertEqual(response.status_code, 200)

    def test_login_page_loads(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user(self):
        response = self.client.post("/signup/", {
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
            "security_question": "What is your pet's name?",
            "security_answer": "Buddy",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="testuser").exists())


class EventRegistrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.category = EventCategory.objects.create(
            name="Test", slug="test"
        )
        self.event = Event.objects.create(
            title="Test Event",
            slug="test-event",
            description="A test event",
            category=self.category,
            date=timezone.now() + timezone.timedelta(days=30),
            location="Test Location",
            capacity=100,
            price=50.00,
            created_by=self.user,
        )
        self.ticket = TicketType.objects.create(
            event=self.event,
            name="General",
            price=50.00,
            quantity_available=100,
        )

    def test_event_detail_loads(self):
        response = self.client.get(f"/events/{self.event.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Event")

    def test_registration_requires_login(self):
        response = self.client.post(f"/events/{self.event.slug}/register/")
        self.assertEqual(response.status_code, 302)

    def test_registration_flow(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            f"/events/{self.event.slug}/register/",
            {"ticket_type": self.ticket.id, "quantity": 2},
        )
        self.assertEqual(response.status_code, 302)
        reg = Registration.objects.get(user=self.user, event=self.event)
        self.assertEqual(reg.quantity, 2)
        self.assertEqual(reg.total_price, 100.00)
        self.assertEqual(reg.status, "confirmed")


class DashboardTest(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)

    def test_dashboard_loads_for_logged_in_user(self):
        User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
