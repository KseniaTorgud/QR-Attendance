from django.conf import settings
from django.db import models

from apps.common.validators import selfie_upload_to
from apps.events.models import Event


class Registration(models.Model):
    class AttendanceStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    id = models.BigAutoField(primary_key=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="registrations"
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    registered_at = models.DateTimeField(auto_now_add=True)
    attendance_marked_by_student = models.BooleanField(default=False)
    attendance_marked_at = models.DateTimeField(null=True, blank=True)
    selfie = models.ImageField(upload_to=selfie_upload_to, null=True, blank=True)
    selfie_uploaded_at = models.DateTimeField(null=True, blank=True)
    attendance_status = models.CharField(
        max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PENDING
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_registrations",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmation_comment = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-registered_at",)
        constraints = [models.UniqueConstraint(fields=("student", "event"), name="uq_student_event_registration")]

    def __str__(self) -> str:
        return f"{self.student_id}:{self.event_id}"
