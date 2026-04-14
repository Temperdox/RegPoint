from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("events/", views.event_list, name="event_list"),
    path("events/create/", views.create_event, name="create_event"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    path(
        "events/<slug:slug>/register/",
        views.register_for_event,
        name="register_for_event",
    ),
    path("signup/", views.signup, name="signup"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path(
        "registration/<str:code>/",
        views.registration_detail,
        name="registration_detail",
    ),
    path(
        "registration/<str:code>/cancel/",
        views.cancel_registration,
        name="cancel_registration",
    ),
    path(
        "admin-dashboard/",
        views.AdminDashboardView.as_view(),
        name="admin_dashboard",
    ),
]
