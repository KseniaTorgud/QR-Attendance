from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "start_at", "registration_deadline", "max_participants")
    list_filter = ("status",)
    search_fields = ("title", "location", "created_by__username")
