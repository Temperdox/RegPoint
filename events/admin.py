from django.contrib import admin

from .models import Event, EventCategory, Registration, TicketType, UserProfile


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 1


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "date", "location", "capacity", "price", "is_active"]
    list_filter = ["is_active", "category", "date"]
    search_fields = ["title", "description", "location"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [TicketTypeInline]


@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = [
        "confirmation_code",
        "user",
        "event",
        "quantity",
        "total_price",
        "status",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["confirmation_code", "user__username", "event__title"]
    readonly_fields = ["confirmation_code"]


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "price", "quantity_available"]
    list_filter = ["event"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "company", "phone", "created_at"]
    search_fields = ["user__username", "company"]
