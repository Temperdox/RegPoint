import secrets

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import EmailOTP, Event, EventCategory, Registration, TicketType

# Generated once per test run so no literal password is ever committed.
TEST_PASSWORD = secrets.token_urlsafe(16)


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
        response = self.client.get(reverse("account_signup"))
        self.assertEqual(response.status_code, 200)

    def test_login_page_loads(self):
        response = self.client.get(reverse("account_login"))
        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user(self):
        response = self.client.post(reverse("account_signup"), {
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "password1": TEST_PASSWORD,
            "password2": TEST_PASSWORD,
            "security_question": "What is your pet's name?",
            "security_answer": "Buddy",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="testuser").exists())


class EventRegistrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password=TEST_PASSWORD
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
        self.client.login(username="testuser", password=TEST_PASSWORD)
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
        User.objects.create_user(username="testuser", password=TEST_PASSWORD)
        self.client.login(username="testuser", password=TEST_PASSWORD)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)


class EmailOTPTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="otpuser", password=TEST_PASSWORD, email="otp@example.com"
        )

    def test_otp_generation(self):
        otp = EmailOTP.generate(user=self.user, channel="email")
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())
        self.assertTrue(otp.is_valid)

    def test_otp_verification(self):
        otp = EmailOTP.generate(user=self.user, channel="email")
        self.assertTrue(otp.verify(otp.code))
        self.assertTrue(otp.is_used)
        # Can't reuse
        self.assertFalse(otp.verify(otp.code))

    def test_otp_wrong_code(self):
        otp = EmailOTP.generate(user=self.user, channel="email")
        self.assertFalse(otp.verify("000000"))

    def test_otp_invalidates_previous(self):
        otp1 = EmailOTP.generate(user=self.user, channel="email")
        otp2 = EmailOTP.generate(user=self.user, channel="email")
        otp1.refresh_from_db()
        self.assertTrue(otp1.is_used)  # Invalidated
        self.assertTrue(otp2.is_valid)  # New one is valid


class AccountSettingsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="settingsuser", password=TEST_PASSWORD, email="s@example.com"
        )
        self.client.login(username="settingsuser", password=TEST_PASSWORD)

    def test_settings_page_loads(self):
        response = self.client.get("/settings/")
        self.assertEqual(response.status_code, 200)

    def test_change_username(self):
        response = self.client.post("/settings/username/", {"new_username": "newname"})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "newname")

    def test_change_username_duplicate(self):
        User.objects.create_user(username="taken", password=TEST_PASSWORD)
        response = self.client.post("/settings/username/", {"new_username": "taken"})
        self.assertEqual(response.status_code, 200)  # Form re-rendered with error

    def test_delete_account(self):
        response = self.client.post("/settings/delete/", {"confirm_text": "DELETE"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="settingsuser").exists())

    def test_delete_account_wrong_confirmation(self):
        response = self.client.post("/settings/delete/", {"confirm_text": "nope"})
        self.assertEqual(response.status_code, 200)  # Re-renders with error
        self.assertTrue(User.objects.filter(username="settingsuser").exists())


class AccountRecoveryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recoverme", password=TEST_PASSWORD, email="recover@example.com"
        )

    def test_recovery_page_loads(self):
        response = self.client.get("/recover/")
        self.assertEqual(response.status_code, 200)

    def test_recovery_does_not_leak_existence(self):
        # Existing user
        response = self.client.post("/recover/", {"identifier": "recover@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recovery Email Sent")
        # Non-existing user - same response
        response = self.client.post("/recover/", {"identifier": "nobody@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recovery Email Sent")

    def test_recovery_by_username(self):
        response = self.client.post("/recover/", {"identifier": "recoverme"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recovery Email Sent")


class AdminUserManagementTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="superadmin", password=TEST_PASSWORD, email="admin@example.com"
        )
        self.regular = User.objects.create_user(
            username="regular", password=TEST_PASSWORD, email="user@example.com"
        )

    def test_manage_users_requires_superuser(self):
        self.client.login(username="regular", password=TEST_PASSWORD)
        response = self.client.get("/admin-dashboard/users/")
        self.assertEqual(response.status_code, 302)

    def test_manage_users_loads_for_superuser(self):
        self.client.login(username="superadmin", password=TEST_PASSWORD)
        response = self.client.get("/admin-dashboard/users/")
        self.assertEqual(response.status_code, 200)

    def test_elevate_user(self):
        self.client.login(username="superadmin", password=TEST_PASSWORD)
        response = self.client.post(
            f"/admin-dashboard/users/{self.regular.pk}/role/",
            {"is_staff": "on", "is_superuser": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_staff)
        self.assertFalse(self.regular.is_superuser)
