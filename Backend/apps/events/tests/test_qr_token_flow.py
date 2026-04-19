"""Интеграционные проверки жизненного цикла QR-токена события (регистрация и смена токена)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.events.models import Event
from apps.events.services import generate_unique_qr_token
from apps.registrations.models import Registration


User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_open_event(teacher, title="QR flow event"):
    now = timezone.now()
    return Event.objects.create(
        title=title,
        location="Hall",
        start_at=now + timedelta(days=3),
        registration_deadline=now + timedelta(days=2),
        max_participants=20,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )


def test_obsolete_qr_token_rejected_after_regenerate(db):
    """После regenerate-qr старый токен из «отсканированного» QR больше не подходит для register-by-qr."""
    teacher = User.objects.create_user("t_qr_obsolete", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_qr_obsolete", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher)
    old_token = event.qr_token
    teacher_client = auth_client(teacher)
    regen = teacher_client.post(reverse("events-regenerate-qr", kwargs={"pk": event.id}))
    assert regen.status_code == status.HTTP_200_OK
    student_client = auth_client(student)
    response = student_client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": old_token},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_fresh_qr_token_works_after_regenerate(db):
    """Новый токен после смены QR успешно проходит register-by-qr."""
    teacher = User.objects.create_user("t_qr_fresh", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_qr_fresh", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher)
    teacher_client = auth_client(teacher)
    regen = teacher_client.post(reverse("events-regenerate-qr", kwargs={"pk": event.id}))
    assert regen.status_code == status.HTTP_200_OK
    new_token = regen.data["qr_token"]
    student_client = auth_client(student)
    response = student_client.post(
        reverse("events-register-by-qr", kwargs={"pk": event.id}),
        {"qr_token": new_token},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert Registration.objects.filter(student=student, event=event).exists()


def test_register_by_qr_requires_qr_token_field(db):
    teacher = User.objects.create_user("t_qr_body", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_qr_body", password="securepass123", role=User.UserRole.STUDENT)
    event = create_open_event(teacher)
    client = auth_client(student)
    response = client.post(reverse("events-register-by-qr", kwargs={"pk": event.id}), {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_each_new_event_gets_distinct_qr_token(db):
    teacher = User.objects.create_user("t_qr_unique", password="securepass123", role=User.UserRole.TEACHER)
    e1 = create_open_event(teacher, title="E1")
    e2 = create_open_event(teacher, title="E2")
    assert e1.qr_token != e2.qr_token
    assert len(e1.qr_token) >= 32


def test_admin_can_regenerate_qr_for_any_event(db):
    admin = User.objects.create_user(
        "admin_qr_regen",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user("t_qr_admin", password="securepass123", role=User.UserRole.TEACHER)
    event = create_open_event(teacher)
    old = event.qr_token
    client = auth_client(admin)
    response = client.post(reverse("events-regenerate-qr", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["qr_token"] != old


def test_generate_unique_qr_token_produces_non_colliding_string(db):
    teacher = User.objects.create_user("t_svc", password="securepass123", role=User.UserRole.TEACHER)
    create_open_event(teacher, title="Existing")
    token = generate_unique_qr_token()
    assert token
    assert not Event.objects.filter(qr_token=token).exists()
