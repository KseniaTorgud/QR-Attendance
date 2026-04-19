from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

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
