import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    security_question = models.CharField(max_length=200, blank=True)
    security_answer = models.CharField(max_length=200, blank=True)
    email_otp_verified = models.BooleanField(default=False)
    sms_otp_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"


class EventCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Event Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    category = models.ForeignKey(
        EventCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=300)
    capacity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return self.title

    @property
    def is_upcoming(self):
        return self.date > timezone.now()

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def tickets_sold(self):
        return sum(
            r.quantity
            for r in self.registrations.filter(status__in=["confirmed", "pending"])
        )

    @property
    def tickets_remaining(self):
        return max(0, self.capacity - self.tickets_sold)

    @property
    def is_sold_out(self):
        return self.tickets_remaining <= 0


class TicketType(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="ticket_types"
    )
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_available = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} - {self.event.title}"

    @property
    def quantity_sold(self):
        return sum(
            r.quantity
            for r in self.registrations.filter(status__in=["confirmed", "pending"])
        )

    @property
    def remaining(self):
        return max(0, self.quantity_available - self.quantity_sold)


class Registration(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="registrations"
    )
    ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registrations",
    )
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    confirmation_code = models.CharField(max_length=32, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.event.title} ({self.confirmation_code})"

    def save(self, *args, **kwargs):
        if not self.confirmation_code:
            self.confirmation_code = uuid.uuid4().hex[:12].upper()
        super().save(*args, **kwargs)


class EmailOTP(models.Model):
    """One-time passcode sent via email or SMS for MFA verification."""

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("sms", "SMS"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otp_codes"
    )
    code = models.CharField(max_length=6)
    channel = models.CharField(max_length=5, choices=CHANNEL_CHOICES, default="email")
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user.username} ({self.channel})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired

    @classmethod
    def generate(cls, user, channel="email", lifetime_minutes=10):
        code = f"{secrets.randbelow(10**6):06d}"
        expires_at = timezone.now() + timezone.timedelta(minutes=lifetime_minutes)
        # Invalidate any existing unused codes for this user/channel
        cls.objects.filter(user=user, channel=channel, is_used=False).update(
            is_used=True
        )
        return cls.objects.create(
            user=user, code=code, channel=channel, expires_at=expires_at
        )

    def verify(self, submitted_code):
        if self.is_valid and self.code == submitted_code:
            self.is_used = True
            self.save(update_fields=["is_used"])
            return True
        return False
