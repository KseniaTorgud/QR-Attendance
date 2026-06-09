import secrets
from typing import Iterable

from django.db.models import Q
from django.utils import timezone


def generate_unique_qr_token() -> str:
    from .models import Event

    while True:
        token = secrets.token_urlsafe(32)
        if not Event.objects.filter(qr_token=token).exists():
            return token


def normalize_full_name(full_name: str) -> str:
    return " ".join((full_name or "").split())


def parse_mandatory_student_names(lines: str = "", names: Iterable[str] = ()) -> list[str]:
    raw_values = []
    if lines:
        raw_values.extend(lines.splitlines())
    if names:
        raw_values.extend(list(names))

    seen = set()
    result = []
    for value in raw_values:
        normalized = normalize_full_name(value)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def add_mandatory_students_to_event(event, full_names: list[str]) -> tuple[int, int]:
    from .models import MandatoryStudent

    existing = {
        name.casefold()
        for name in MandatoryStudent.objects.filter(event=event).values_list("full_name", flat=True)
    }
    to_create = []
    for full_name in full_names:
        if full_name.casefold() in existing:
            continue
        to_create.append(MandatoryStudent(event=event, full_name=full_name))
        existing.add(full_name.casefold())

    created = MandatoryStudent.objects.bulk_create(to_create)
    total = MandatoryStudent.objects.filter(event=event).count()
    return len(created), total


def sync_mandatory_selfies_after_event(event) -> None:
    from .models import MandatoryStudent
    from apps.registrations.models import Registration

    if timezone.now() < event.start_at:
        return

    mandatory_students = MandatoryStudent.objects.filter(event=event).filter(
        Q(selfie="") | Q(selfie__isnull=True)
    )
    if not mandatory_students.exists():
        return

    registrations = (
        Registration.objects.filter(
            event=event,
            attendance_status=Registration.AttendanceStatus.CONFIRMED,
            selfie__isnull=False,
        )
        .exclude(selfie="")
        .select_related("student")
    )
    registration_map = {}
    for registration in registrations:
        full_name = normalize_full_name(registration.full_name)
        if not full_name:
            full_name = normalize_full_name(f"{registration.student.last_name} {registration.student.first_name}")
        if not full_name:
            full_name = normalize_full_name(
                f"{registration.student.first_name} {registration.student.last_name}"
            )
        if full_name:
            registration_map.setdefault(full_name.casefold(), registration)

    for mandatory in mandatory_students:
        match = registration_map.get(mandatory.full_name.casefold())
        if not match:
            continue
        mandatory.selfie = match.selfie
        mandatory.selfie_uploaded_at = match.selfie_uploaded_at or timezone.now()
        mandatory.save(update_fields=["selfie", "selfie_uploaded_at", "updated_at"])
