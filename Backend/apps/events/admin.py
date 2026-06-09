from django.contrib import admin

from .models import Event, MandatoryStudent


class MandatoryStudentInline(admin.TabularInline):
    model = MandatoryStudent
    extra = 0
    fields = ("full_name", "attended", "attendance_marked_at", "selfie")
    readonly_fields = ("attendance_marked_at",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "start_at", "registration_deadline", "max_participants")
    list_filter = ("status",)
    search_fields = ("title", "location", "created_by__username")
    inlines = (MandatoryStudentInline,)


@admin.register(MandatoryStudent)
class MandatoryStudentAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "full_name", "attended", "attendance_marked_at")
    list_filter = ("attended",)
    search_fields = ("full_name", "event__title")
