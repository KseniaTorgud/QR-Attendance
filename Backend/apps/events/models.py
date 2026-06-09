from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.validators import mandatory_selfie_upload_to

from .services import generate_unique_qr_token


class Event(models.Model):
    class EventStatus(models.TextChoices):
        REGISTRATION_OPEN = "registration_open", "Registration open"
        CONFIRMATION_REQUIRED = "confirmation_required", "Confirmation required"
        FINISHED = "finished", "Finished"

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255)
    start_at = models.DateTimeField()
    registration_deadline = models.DateTimeField()
    max_participants = models.PositiveIntegerField()
    status = models.CharField(
        max_length=30, choices=EventStatus.choices, default=EventStatus.REGISTRATION_OPEN
    )
    qr_token = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_at",)

    def clean(self):
        if self.registration_deadline > self.start_at:
            raise ValidationError({"registration_deadline": "Registration deadline must be <= start time."})
        if self.max_participants <= 0:
            raise ValidationError({"max_participants": "Max participants must be greater than 0."})

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = generate_unique_qr_token()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class MandatoryStudent(models.Model):
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="mandatory_students")
    full_name = models.CharField(max_length=255)
    attended = models.BooleanField(null=True, blank=True)
    attendance_marked_at = models.DateTimeField(null=True, blank=True)
    selfie = models.ImageField(upload_to=mandatory_selfie_upload_to, null=True, blank=True)
    selfie_uploaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)
        constraints = [models.UniqueConstraint(fields=("event", "full_name"), name="uq_event_mandatory_full_name")]

    def __str__(self) -> str:
        return f"{self.event_id}:{self.full_name}"
