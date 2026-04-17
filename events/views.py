from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views import View

from .forms import (
    AccountDeleteForm,
    AccountRecoveryForm,
    AdminUserRoleForm,
    ChangeEmailForm,
    ChangeUsernameForm,
    EmailOTPForm,
    EventForm,
    IdentityVerifyForm,
    RegistrationForm,
    TicketTypeForm,
    UserProfileForm,
)
from .models import EmailOTP, Event, EventCategory, Registration, TicketType

ACCESS_DENIED = "Access denied."
MAX_TICKET_TYPES = 20


# --- Public Views ---


def home(request):
    upcoming_events = Event.objects.filter(
        is_active=True, date__gte=timezone.now()
    ).select_related("category", "created_by")[:6]
    categories = EventCategory.objects.all()
    total_events = Event.objects.filter(is_active=True).count()
    total_registrations = Registration.objects.filter(
        status__in=["confirmed", "pending"]
    ).count()
    context = {
        "upcoming_events": upcoming_events,
        "categories": categories,
        "total_events": total_events,
        "total_registrations": total_registrations,
    }
    return render(request, "events/home.html", context)


def event_list(request):
    events = Event.objects.filter(is_active=True).select_related(
        "category", "created_by"
    )

    # Filter by category
    category_slug = request.GET.get("category")
    if category_slug:
        events = events.filter(category__slug=category_slug)

    # Filter upcoming only
    show = request.GET.get("show", "upcoming")
    if show == "upcoming":
        events = events.filter(date__gte=timezone.now())
    elif show == "past":
        events = events.filter(date__lt=timezone.now())

    # Search
    query = request.GET.get("q")
    if query:
        events = events.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
        )

    categories = EventCategory.objects.all()
    context = {
        "events": events,
        "categories": categories,
        "current_category": category_slug,
        "current_show": show,
        "query": query or "",
    }
    return render(request, "events/event_list.html", context)


def event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.select_related("category", "created_by").prefetch_related(
            "ticket_types"
        ),
        slug=slug,
    )
    registration_form = None
    user_registration = None

    if request.user.is_authenticated:
        user_registration = Registration.objects.filter(
            user=request.user, event=event
        ).exclude(status="cancelled").first()
        if not user_registration and event.is_upcoming and not event.is_sold_out:
            registration_form = RegistrationForm(event=event)

    context = {
        "event": event,
        "registration_form": registration_form,
        "user_registration": user_registration,
    }
    return render(request, "events/event_detail.html", context)


# --- Email/SMS OTP MFA Views ---


@login_required
def mfa_otp_setup(request):
    """Send an OTP code via email (or SMS) and redirect to verification."""
    channel = request.GET.get("channel", "email")
    if channel not in ("email", "sms"):
        channel = "email"

    otp = EmailOTP.generate(user=request.user, channel=channel)

    if channel == "email":
        from django.core.mail import send_mail

        send_mail(
            subject="RegPoint - Your verification code",
            message=f"Your RegPoint verification code is: {otp.code}\n\nThis code expires in 10 minutes.",
            from_email=None,
            recipient_list=[request.user.email],
            fail_silently=True,
        )
        messages.info(request, f"Verification code sent to {request.user.email}.")
    else:
        # SMS placeholder - integrate with Twilio/SNS in production
        messages.info(
            request,
            f"SMS verification code: {otp.code} (In production, this would be sent via SMS.)",
        )

    return redirect(f"{request.build_absolute_uri('/accounts/mfa/otp/verify/')}?channel={channel}")


def _consume_otp(user, channel, submitted_code):
    """Look up the active OTP for this user/channel and verify the submitted code.
    On success, mark the corresponding profile flag and return True."""
    otp = (
        EmailOTP.objects.filter(user=user, channel=channel, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if not (otp and otp.verify(submitted_code)):
        return False

    profile = user.profile
    if channel == "email":
        profile.email_otp_verified = True
    else:
        profile.sms_otp_verified = True
    profile.save()
    return True


@login_required
def mfa_otp_verify(request):
    """Verify the submitted OTP code."""
    channel = request.GET.get("channel", "email")

    if request.method != "POST":
        return render(
            request,
            "events/mfa_otp_verify.html",
            {"form": EmailOTPForm(), "channel": channel},
        )

    form = EmailOTPForm(request.POST)
    if form.is_valid() and _consume_otp(request.user, channel, form.cleaned_data["code"]):
        label = "Email" if channel == "email" else "SMS"
        messages.success(request, f"{label} verification successful!")
        return redirect("profile")

    if form.is_valid():
        messages.error(request, "Invalid or expired code. Please try again.")

    return render(
        request,
        "events/mfa_otp_verify.html",
        {"form": form, "channel": channel},
    )


# --- User Dashboard ---


@login_required
def dashboard(request):
    registrations = Registration.objects.filter(user=request.user).select_related(
        "event", "ticket_type"
    )
    upcoming_regs = registrations.filter(
        event__date__gte=timezone.now()
    ).exclude(status="cancelled")
    past_regs = registrations.filter(event__date__lt=timezone.now())
    total_spent = registrations.filter(
        status__in=["confirmed", "pending"]
    ).aggregate(total=Sum("total_price"))["total"] or Decimal("0")

    context = {
        "upcoming_regs": upcoming_regs,
        "past_regs": past_regs,
        "total_spent": total_spent,
        "total_registrations": registrations.exclude(status="cancelled").count(),
    }
    return render(request, "events/dashboard.html", context)


@login_required
def profile(request):
    user_profile = request.user.profile
    if request.method == "POST":
        form = UserProfileForm(
            request.POST, request.FILES, instance=user_profile, user=request.user
        )
        if form.is_valid():
            form.save()
            request.user.first_name = form.cleaned_data["first_name"]
            request.user.last_name = form.cleaned_data["last_name"]
            request.user.email = form.cleaned_data["email"]
            request.user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("profile")
    else:
        form = UserProfileForm(instance=user_profile, user=request.user)
    return render(request, "events/profile.html", {"form": form})


# --- Registration / Ticket Purchase ---


@login_required
def register_for_event(request, slug):
    event = get_object_or_404(Event, slug=slug, is_active=True)

    # Check if already registered
    existing = Registration.objects.filter(
        user=request.user, event=event
    ).exclude(status="cancelled").first()
    if existing:
        messages.warning(request, "You are already registered for this event.")
        return redirect("event_detail", slug=slug)

    if not event.is_upcoming:
        messages.error(request, "This event has already passed.")
        return redirect("event_detail", slug=slug)

    if request.method == "POST":
        form = RegistrationForm(request.POST, event=event)
        if form.is_valid():
            ticket_type = form.cleaned_data["ticket_type"]
            quantity = form.cleaned_data["quantity"]

            if quantity > ticket_type.remaining:
                messages.error(
                    request,
                    f"Only {ticket_type.remaining} tickets remaining for {ticket_type.name}.",
                )
                return redirect("event_detail", slug=slug)

            total = ticket_type.price * quantity
            registration = Registration.objects.create(
                user=request.user,
                event=event,
                ticket_type=ticket_type,
                quantity=quantity,
                total_price=total,
                status="confirmed",
            )
            messages.success(
                request,
                f"Registration confirmed! Your confirmation code is {registration.confirmation_code}.",
            )
            return redirect("registration_detail", code=registration.confirmation_code)
    else:
        form = RegistrationForm(event=event)

    return render(
        request,
        "events/register_event.html",
        {"form": form, "event": event},
    )


@login_required
def registration_detail(request, code):
    registration = get_object_or_404(
        Registration.objects.select_related("event", "ticket_type"),
        confirmation_code=code,
        user=request.user,
    )
    return render(
        request, "events/registration_detail.html", {"registration": registration}
    )


@login_required
def cancel_registration(request, code):
    registration = get_object_or_404(
        Registration, confirmation_code=code, user=request.user
    )
    if request.method == "POST":
        if registration.status != "cancelled":
            registration.status = "cancelled"
            registration.save()
            messages.success(request, "Registration cancelled successfully.")
        return redirect("dashboard")
    return render(
        request, "events/cancel_registration.html", {"registration": registration}
    )


# --- Admin / Staff Views ---


class AdminDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_staff:
            messages.error(request, ACCESS_DENIED)
            return redirect("home")

        total_events = Event.objects.count()
        active_events = Event.objects.filter(is_active=True).count()
        total_registrations = Registration.objects.exclude(status="cancelled").count()
        total_revenue = Registration.objects.filter(
            status__in=["confirmed", "pending"]
        ).aggregate(total=Sum("total_price"))["total"] or Decimal("0")

        recent_registrations = Registration.objects.select_related(
            "user", "event"
        ).order_by("-created_at")[:10]

        # Events with registration counts
        events_with_stats = (
            Event.objects.filter(is_active=True)
            .annotate(
                reg_count=Count(
                    "registrations",
                    filter=Q(registrations__status__in=["confirmed", "pending"]),
                ),
                revenue=Sum(
                    "registrations__total_price",
                    filter=Q(registrations__status__in=["confirmed", "pending"]),
                ),
            )
            .order_by("-date")[:10]
        )

        # Registrations by status
        status_counts = (
            Registration.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        context = {
            "total_events": total_events,
            "active_events": active_events,
            "total_registrations": total_registrations,
            "total_revenue": total_revenue,
            "recent_registrations": recent_registrations,
            "events_with_stats": events_with_stats,
            "status_counts": status_counts,
        }
        return render(request, "events/admin_dashboard.html", context)


def _parse_ticket_count(post_data):
    """Parse and clamp the user-supplied ticket_count (DoS guard)."""
    try:
        count = int(post_data.get("ticket_count", 1))
    except (TypeError, ValueError):
        count = 1
    return max(1, min(count, MAX_TICKET_TYPES))


def _build_ticket_forms(post_data, ticket_count):
    return [
        TicketTypeForm(post_data, prefix=f"ticket_{i}")
        for i in range(ticket_count)
    ]


def _generate_unique_event_slug(title):
    base = slugify(title)
    slug = base
    counter = 1
    while Event.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _save_event_with_tickets(form, ticket_forms, user):
    event = form.save(commit=False)
    event.created_by = user
    event.slug = _generate_unique_event_slug(event.title)
    event.save()
    for tf in ticket_forms:
        ticket = tf.save(commit=False)
        ticket.event = event
        ticket.save()
    return event


@login_required
def create_event(request):
    if not request.user.is_staff:
        messages.error(request, ACCESS_DENIED)
        return redirect("home")

    if request.method != "POST":
        return render(
            request,
            "events/create_event.html",
            {"form": EventForm(), "ticket_forms": [TicketTypeForm(prefix="ticket_0")]},
        )

    form = EventForm(request.POST)
    ticket_forms = _build_ticket_forms(request.POST, _parse_ticket_count(request.POST))

    if form.is_valid() and all(tf.is_valid() for tf in ticket_forms):
        event = _save_event_with_tickets(form, ticket_forms, request.user)
        messages.success(request, f'Event "{event.title}" created successfully.')
        return redirect("event_detail", slug=event.slug)

    return render(
        request,
        "events/create_event.html",
        {"form": form, "ticket_forms": ticket_forms},
    )


# --- Identity Verification Helper ---


def _verify_identity(request, method, credential):
    """Verify the user's identity via password or OTP. Returns True if valid."""
    if method == "password":
        return check_password(credential, request.user.password)
    elif method in ("email_otp", "sms_otp"):
        channel = "email" if method == "email_otp" else "sms"
        otp = (
            EmailOTP.objects.filter(
                user=request.user, channel=channel, is_used=False
            )
            .order_by("-created_at")
            .first()
        )
        if otp and otp.verify(credential):
            return True
    return False


# --- Account Settings ---


@login_required
def account_settings(request):
    """Main account settings page."""
    return render(request, "events/account_settings.html")


@login_required
def change_username(request):
    if request.method == "POST":
        form = ChangeUsernameForm(request.POST, current_user=request.user)
        if form.is_valid():
            request.user.username = form.cleaned_data["new_username"]
            request.user.save()
            messages.success(request, "Username updated successfully.")
            return redirect("account_settings")
    else:
        form = ChangeUsernameForm(current_user=request.user)
        form.fields["new_username"].initial = request.user.username
    return render(request, "events/change_username.html", {"form": form})


@login_required
def change_email_request(request):
    """Step 1: user requests to change email. Step 2: verify identity."""
    # Check if already verified in this session
    if request.session.get("identity_verified_for") == "change_email":
        return redirect("change_email_confirm")

    if request.method == "POST":
        verify_form = IdentityVerifyForm(request.POST)
        if verify_form.is_valid():
            method = verify_form.cleaned_data["method"]
            credential = verify_form.cleaned_data["credential"]
            if _verify_identity(request, method, credential):
                request.session["identity_verified_for"] = "change_email"
                return redirect("change_email_confirm")
            else:
                messages.error(request, "Identity verification failed.")
    else:
        verify_form = IdentityVerifyForm()

    return render(
        request,
        "events/verify_identity.html",
        {
            "form": verify_form,
            "action_name": "Change Email",
            "send_otp_url_email": "/accounts/mfa/otp/?channel=email",
            "send_otp_url_sms": "/accounts/mfa/otp/?channel=sms",
        },
    )


@login_required
def change_email_confirm(request):
    """Step 2: Actually change the email after identity verification."""
    if request.session.get("identity_verified_for") != "change_email":
        return redirect("change_email_request")

    if request.method == "POST":
        form = ChangeEmailForm(request.POST)
        if form.is_valid():
            request.user.email = form.cleaned_data["new_email"]
            request.user.save()
            # Clear verification
            del request.session["identity_verified_for"]
            messages.success(request, "Email updated successfully.")
            return redirect("account_settings")
    else:
        form = ChangeEmailForm()
        form.fields["new_email"].initial = request.user.email
    return render(request, "events/change_email.html", {"form": form})


@login_required
def change_password_request(request):
    """Verify identity before allowing password change."""
    if request.session.get("identity_verified_for") == "change_password":
        return redirect("account_change_password")

    if request.method == "POST":
        verify_form = IdentityVerifyForm(request.POST)
        if verify_form.is_valid():
            method = verify_form.cleaned_data["method"]
            credential = verify_form.cleaned_data["credential"]
            if _verify_identity(request, method, credential):
                request.session["identity_verified_for"] = "change_password"
                return redirect("account_change_password")
            else:
                messages.error(request, "Identity verification failed.")
    else:
        verify_form = IdentityVerifyForm()

    return render(
        request,
        "events/verify_identity.html",
        {
            "form": verify_form,
            "action_name": "Change Password",
            "send_otp_url_email": "/accounts/mfa/otp/?channel=email",
            "send_otp_url_sms": "/accounts/mfa/otp/?channel=sms",
        },
    )


# --- Account Deletion ---


@login_required
def delete_account(request):
    if request.method == "POST":
        form = AccountDeleteForm(request.POST)
        if form.is_valid():
            user = request.user
            from django.contrib.auth import logout

            logout(request)
            user.delete()
            messages.success(
                request, "Your account has been permanently deleted."
            )
            return redirect("home")
    else:
        form = AccountDeleteForm()
    return render(request, "events/delete_account.html", {"form": form})


# --- Account Recovery (does NOT leak user existence) ---


def account_recovery(request):
    """Accept email, username, or phone. Always show the same message."""
    sent = False
    if request.method == "POST":
        form = AccountRecoveryForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"].strip()
            # Look up user by email, username, or phone — silently
            user = (
                User.objects.filter(
                    Q(email__iexact=identifier)
                    | Q(username__iexact=identifier)
                    | Q(profile__phone=identifier)
                )
                .first()
            )
            if user and user.email:
                # Generate a password-reset-style token via allauth
                from allauth.account.forms import ResetPasswordForm

                rpf = ResetPasswordForm({"email": user.email})
                if rpf.is_valid():
                    rpf.save(request)
            # Always show the same message regardless
            sent = True
    else:
        form = AccountRecoveryForm()

    return render(
        request,
        "events/account_recovery.html",
        {"form": form, "sent": sent},
    )


# --- Admin User Elevation ---


@login_required
def admin_manage_users(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser required.")
        return redirect("home")

    query = request.GET.get("q", "")
    users = User.objects.select_related("profile").order_by("-date_joined")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    return render(
        request,
        "events/admin_manage_users.html",
        {"users": users[:50], "query": query},
    )


@login_required
def admin_edit_user_role(request, user_id):
    if not request.user.is_superuser:
        messages.error(request, ACCESS_DENIED)
        return redirect("home")

    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = AdminUserRoleForm(request.POST)
        if form.is_valid():
            target_user.is_staff = form.cleaned_data["is_staff"]
            target_user.is_superuser = form.cleaned_data["is_superuser"]
            target_user.save()
            messages.success(
                request,
                f"Roles updated for {target_user.username}.",
            )
            return redirect("admin_manage_users")
    else:
        form = AdminUserRoleForm(initial={
            "is_staff": target_user.is_staff,
            "is_superuser": target_user.is_superuser,
        })

    return render(
        request,
        "events/admin_edit_user_role.html",
        {"form": form, "target_user": target_user},
    )
