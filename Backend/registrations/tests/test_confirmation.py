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


def create_event_and_registration(owner_teacher, student, title="Confirm event"):
    event = Event.objects.create(
        title=title,
        location="Room D",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=owner_teacher,
    )
    return Registration.objects.create(student=student, event=event)


def test_teacher_can_confirm_registration_only_for_own_event(db):
    teacher = User.objects.create_user("teacher_confirm", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_confirm", password="securepass123", role=User.UserRole.STUDENT)
    registration = create_event_and_registration(teacher, student)
    client = auth_client(teacher)

    response = client.patch(
        reverse("registrations-confirm", kwargs={"pk": registration.id}),
        {"attendance_status": Registration.AttendanceStatus.CONFIRMED},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.attendance_status == Registration.AttendanceStatus.CONFIRMED


def test_teacher_cannot_confirm_registration_for_foreign_event(db):
    owner_teacher = User.objects.create_user(
        "teacher_owner_confirm",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    foreign_teacher = User.objects.create_user(
        "teacher_foreign_confirm",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    student = User.objects.create_user("student_foreign_confirm", password="securepass123", role=User.UserRole.STUDENT)
    registration = create_event_and_registration(owner_teacher, student, title="Foreign event")
    client = auth_client(foreign_teacher)

    response = client.patch(
        reverse("registrations-confirm", kwargs={"pk": registration.id}),
        {"attendance_status": Registration.AttendanceStatus.REJECTED},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_admin_can_confirm_any_registration(db):
    teacher = User.objects.create_user("teacher_any_confirm", password="securepass123", role=User.UserRole.TEACHER)
    admin = User.objects.create_user(
        "admin_confirm",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    student = User.objects.create_user("student_any_confirm", password="securepass123", role=User.UserRole.STUDENT)
    registration = create_event_and_registration(teacher, student, title="Any event")
    client = auth_client(admin)

    response = client.patch(
        reverse("registrations-confirm", kwargs={"pk": registration.id}),
        {
            "attendance_status": Registration.AttendanceStatus.CONFIRMED,
            "confirmation_comment": "Looks good",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.confirmed_by_id == admin.id
