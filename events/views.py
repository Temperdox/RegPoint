from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views import View

from .forms import (
    EventForm,
    RegistrationForm,
    SignUpForm,
    TicketTypeForm,
    UserProfileForm,
)
from .models import Event, EventCategory, Registration, TicketType


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


# --- Auth Views ---


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]
            user.save()
            # Update profile (created by signal)
            user.profile.phone = form.cleaned_data.get("phone", "")
            user.profile.company = form.cleaned_data.get("company", "")
            user.profile.security_question = form.cleaned_data["security_question"]
            user.profile.security_answer = form.cleaned_data["security_answer"]
            user.profile.save()
            login(request, user)
            messages.success(request, "Account created successfully! Welcome to RegPoint.")
            return redirect("home")
    else:
        form = SignUpForm()
    return render(request, "events/signup.html", {"form": form})


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
        form = UserProfileForm(request.POST, instance=user_profile, user=request.user)
        if form.is_valid():
            profile_obj = form.save()
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
            messages.error(request, "Access denied.")
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


@login_required
def create_event(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect("home")

    if request.method == "POST":
        form = EventForm(request.POST)
        ticket_forms = []
        # Collect ticket type data from POST
        ticket_count = int(request.POST.get("ticket_count", 1))
        for i in range(ticket_count):
            prefix = f"ticket_{i}"
            ticket_forms.append(
                TicketTypeForm(request.POST, prefix=prefix)
            )

        if form.is_valid() and all(tf.is_valid() for tf in ticket_forms):
            event = form.save(commit=False)
            event.created_by = request.user
            event.slug = slugify(event.title)
            # Ensure unique slug
            base_slug = event.slug
            counter = 1
            while Event.objects.filter(slug=event.slug).exists():
                event.slug = f"{base_slug}-{counter}"
                counter += 1
            event.save()

            for tf in ticket_forms:
                ticket = tf.save(commit=False)
                ticket.event = event
                ticket.save()

            messages.success(request, f'Event "{event.title}" created successfully.')
            return redirect("event_detail", slug=event.slug)
    else:
        form = EventForm()
        ticket_forms = [TicketTypeForm(prefix="ticket_0")]

    return render(
        request,
        "events/create_event.html",
        {"form": form, "ticket_forms": ticket_forms},
    )
