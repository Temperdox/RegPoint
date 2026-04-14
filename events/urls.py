from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    # Events
    path("events/", views.event_list, name="event_list"),
    path("events/create/", views.create_event, name="create_event"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    path(
        "events/<slug:slug>/register/",
        views.register_for_event,
        name="register_for_event",
    ),
    # OTP MFA
    path("accounts/mfa/otp/", views.mfa_otp_setup, name="mfa_otp_setup"),
    path("accounts/mfa/otp/verify/", views.mfa_otp_verify, name="mfa_otp_verify"),
    # User Dashboard & Profile
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    # Account Settings
    path("settings/", views.account_settings, name="account_settings"),
    path("settings/username/", views.change_username, name="change_username"),
    path("settings/email/", views.change_email_request, name="change_email_request"),
    path("settings/email/confirm/", views.change_email_confirm, name="change_email_confirm"),
    path("settings/password/", views.change_password_request, name="change_password_request"),
    path("settings/delete/", views.delete_account, name="delete_account"),
    # Account Recovery
    path("recover/", views.account_recovery, name="account_recovery"),
    # Registrations
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
    # Admin
    path(
        "admin-dashboard/",
        views.AdminDashboardView.as_view(),
        name="admin_dashboard",
    ),
    path("admin-dashboard/users/", views.admin_manage_users, name="admin_manage_users"),
    path(
        "admin-dashboard/users/<int:user_id>/role/",
        views.admin_edit_user_role,
        name="admin_edit_user_role",
    ),
]
