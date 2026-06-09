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


def _default_registration_full_name(student) -> str:
    full_name = f"{student.last_name} {student.first_name}".strip()
    if full_name:
        return " ".join(full_name.split())
    fallback = f"{student.first_name} {student.last_name}".strip()
    if fallback:
        return " ".join(fallback.split())
    return student.username


def create_registration(student, event: Event, full_name: str = "", group: str = "") -> Registration:
    clean_full_name = " ".join((full_name or "").split())
    clean_group = " ".join((group or "").split())
    if not clean_full_name:
        clean_full_name = _default_registration_full_name(student)
    return Registration.objects.create(
        student=student,
        event=event,
        full_name=clean_full_name,
        group=clean_group,
    )
