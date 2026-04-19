from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.exceptions import ConflictError
from apps.events.models import Event

from .models import Registration


def validate_registration_by_qr(student, event: Event, qr_token: str) -> None:
    if qr_token != event.qr_token:
        raise ValidationError({"detail": "Invalid QR token."})

    if event.status != Event.EventStatus.REGISTRATION_OPEN:
        raise ValidationError({"detail": "Event is not open for registration."})

    if timezone.now() > event.registration_deadline:
        raise ValidationError({"detail": "Registration deadline has passed."})

    if Registration.objects.filter(student=student, event=event).exists():
        raise ConflictError("Student is already registered for this event.")

    current_count = Registration.objects.filter(event=event).count()
    if current_count >= event.max_participants:
        raise ConflictError("Event has reached maximum participants limit.")


def create_registration(student, event: Event) -> Registration:
    return Registration.objects.create(student=student, event=event)
