from django.contrib import admin

from .models import Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "event",
        "attendance_marked_by_student",
        "attendance_status",
        "confirmed_by",
    )
    list_filter = ("attendance_status", "attendance_marked_by_student")
    search_fields = ("student__username", "event__title")
