from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.events.models import Event
from apps.registrations.models import Registration


User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_open_event(teacher, max_participants=10):
    now = timezone.now()
    return Event.objects.create(
        title="Open event",
        location="Lab 1",
        start_at=now + timedelta(days=2),
        registration_deadline=now + timedelta(days=1),
        max_participants=max_participants,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )


def test_student_can_register_by_valid_qr(db):
    teacher = User.objects.create_user("teacher_qr", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_qr", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher)
    client = auth_client(student)

    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert Registration.objects.filter(student=student, event=event).exists()


def test_student_cannot_register_with_invalid_qr(db):
    teacher = User.objects.create_user("teacher_invalid", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_invalid", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher)
    client = auth_client(student)

    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": "bad-token"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_student_cannot_register_twice(db):
    teacher = User.objects.create_user("teacher_twice", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_twice", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher)
    Registration.objects.create(student=student, event=event)
    client = auth_client(student)

    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT


def test_student_cannot_register_after_deadline(db):
    teacher = User.objects.create_user("teacher_deadline", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_deadline", password="securepass123", role=User.UserRole.STUDENT)
    now = timezone.now()
    event = Event.objects.create(
        title="Closed event",
        location="Lab 2",
        start_at=now + timedelta(days=1),
        registration_deadline=now - timedelta(hours=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    client = auth_client(student)

    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_student_cannot_register_when_limit_reached(db):
    teacher = User.objects.create_user("teacher_limit", password="securepass123", role=User.UserRole.TEACHER)
    student1 = User.objects.create_user("student_limit_1", password="securepass123", role=User.UserRole.STUDENT)
    student2 = User.objects.create_user("student_limit_2", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher, max_participants=1)
    Registration.objects.create(student=student1, event=event)
    client = auth_client(student2)

    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT


def test_teacher_cannot_register_by_qr(db):
    teacher = User.objects.create_user("teacher_qr_fail", password="securepass123", role=User.UserRole.TEACHER)
    event = create_open_event(teacher)
    client = auth_client(teacher)
    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_student_cannot_register_when_event_not_open(db):
    teacher = User.objects.create_user("teacher_closed", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_closed", password="securepass123", role=User.UserRole.STUDENT)
    now = timezone.now()
    event = Event.objects.create(
        title="Finished",
        location="L",
        start_at=now + timedelta(days=2),
        registration_deadline=now + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.FINISHED,
        created_by=teacher,
    )
    client = auth_client(student)
    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_student_cannot_register_with_token_from_another_event(db):
    teacher = User.objects.create_user("teacher_mismatch", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_mismatch", password="securepass123", role=User.UserRole.STUDENT)
    event_a = create_open_event(teacher, max_participants=10)
    event_b = create_open_event(teacher, max_participants=10)
    client = auth_client(student)
    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event_a.id}),
        {"qr_token": event_b.qr_token},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_student_cannot_register_when_confirmation_required(db):
    teacher = User.objects.create_user("teacher_confreq", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_confreq", password="securepass123", role=User.UserRole.STUDENT)
    now = timezone.now()
    event = Event.objects.create(
        title="Confirm phase",
        location="L",
        start_at=now + timedelta(days=2),
        registration_deadline=now + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.CONFIRMATION_REQUIRED,
        created_by=teacher,
    )
    client = auth_client(student)
    response = client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": event.qr_token},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
