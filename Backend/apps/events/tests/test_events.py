from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.events.models import Event


User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def event_payload():
    now = timezone.now()
    return {
        "title": "Backend workshop",
        "description": "Intro",
        "location": "Auditorium",
        "start_at": (now + timedelta(days=2)).isoformat(),
        "registration_deadline": (now + timedelta(days=1)).isoformat(),
        "max_participants": 10,
        "status": Event.EventStatus.REGISTRATION_OPEN,
    }


def test_teacher_can_create_event_with_qr(db):
    teacher = User.objects.create_user(
        username="teacher_create",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    client = auth_client(teacher)

    response = client.post(reverse("events-list"), event_payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["qr_token"]


def test_teacher_cannot_update_foreign_event(db):
    owner = User.objects.create_user(
        username="teacher_owner",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    another_teacher = User.objects.create_user(
        username="teacher_other",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    event = Event.objects.create(
        title="ML meetup",
        location="Room 101",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=20,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=owner,
    )
    client = auth_client(another_teacher)

    response = client.patch(
        reverse("events-detail", kwargs={"pk": event.id}),
        {"title": "Updated title"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_student_cannot_get_events_list_but_can_get_event_by_id(db):
    teacher = User.objects.create_user(
        username="teacher_for_student",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    student = User.objects.create_user(
        username="student_events",
        password="securepass123",
        role=User.UserRole.STUDENT,
    )
    event = Event.objects.create(
        title="Security lecture",
        location="Main hall",
        start_at=timezone.now() + timedelta(days=5),
        registration_deadline=timezone.now() + timedelta(days=4),
        max_participants=30,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    client = auth_client(student)

    list_response = client.get(reverse("events-list"))
    detail_response = client.get(reverse("events-detail", kwargs={"pk": event.id}))

    assert list_response.status_code == status.HTTP_403_FORBIDDEN
    assert detail_response.status_code == status.HTTP_200_OK


def test_admin_can_list_events(db):
    admin = User.objects.create_user(
        "admin_events_list",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user(
        "teacher_events_list",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    Event.objects.create(
        title="E1",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    client = auth_client(admin)
    response = client.get(reverse("events-list"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"]


def test_teacher_mine_filter_returns_only_own_events(db):
    teacher_a = User.objects.create_user("teacher_mine_a", password="securepass123", role=User.UserRole.TEACHER)
    teacher_b = User.objects.create_user("teacher_mine_b", password="securepass123", role=User.UserRole.TEACHER)
    Event.objects.create(
        title="Owned",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher_a,
    )
    Event.objects.create(
        title="Other",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher_b,
    )
    client = auth_client(teacher_a)
    response = client.get(reverse("events-list"), {"mine": "true"})
    assert response.status_code == status.HTTP_200_OK
    titles = {row["title"] for row in response.data["results"]}
    assert titles == {"Owned"}


def test_owner_regenerates_qr_token(db):
    teacher = User.objects.create_user("teacher_regen", password="securepass123", role=User.UserRole.TEACHER)
    event = Event.objects.create(
        title="Regen",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    old = event.qr_token
    client = auth_client(teacher)
    response = client.post(reverse("events-regenerate-qr", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["qr_token"] != old
    event.refresh_from_db()
    assert event.qr_token == response.data["qr_token"]


def test_foreign_teacher_cannot_regenerate_qr(db):
    owner = User.objects.create_user("owner_regen", password="securepass123", role=User.UserRole.TEACHER)
    other = User.objects.create_user("other_regen", password="securepass123", role=User.UserRole.TEACHER)
    event = Event.objects.create(
        title="Foreign regen",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=owner,
    )
    client = auth_client(other)
    response = client.post(reverse("events-regenerate-qr", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_student_cannot_regenerate_qr(db):
    teacher = User.objects.create_user("teacher_for_regen", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_regen", password="securepass123", role=User.UserRole.STUDENT)
    event = Event.objects.create(
        title="Student regen",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    client = auth_client(student)
    response = client.post(reverse("events-regenerate-qr", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_owner_can_delete_event(db):
    teacher = User.objects.create_user("teacher_delete", password="securepass123", role=User.UserRole.TEACHER)
    event = Event.objects.create(
        title="Delete me",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    client = auth_client(teacher)
    response = client.delete(reverse("events-detail", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Event.objects.filter(pk=event.id).exists()


def test_foreign_teacher_cannot_delete_event(db):
    owner = User.objects.create_user("owner_delete", password="securepass123", role=User.UserRole.TEACHER)
    other = User.objects.create_user("other_delete", password="securepass123", role=User.UserRole.TEACHER)
    event = Event.objects.create(
        title="No delete",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=owner,
    )
    client = auth_client(other)
    response = client.delete(reverse("events-detail", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_event_rejects_deadline_after_start(db):
    teacher = User.objects.create_user("teacher_invalid", password="securepass123", role=User.UserRole.TEACHER)
    client = auth_client(teacher)
    now = timezone.now()
    payload = {
        "title": "Bad dates",
        "description": "",
        "location": "L",
        "start_at": (now + timedelta(days=1)).isoformat(),
        "registration_deadline": (now + timedelta(days=2)).isoformat(),
        "max_participants": 5,
        "status": Event.EventStatus.REGISTRATION_OPEN,
    }
    response = client.post(reverse("events-list"), payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_create_event_rejects_non_positive_max_participants(db):
    teacher = User.objects.create_user("teacher_max0", password="securepass123", role=User.UserRole.TEACHER)
    client = auth_client(teacher)
    now = timezone.now()
    payload = {
        "title": "Bad cap",
        "description": "",
        "location": "L",
        "start_at": (now + timedelta(days=2)).isoformat(),
        "registration_deadline": (now + timedelta(days=1)).isoformat(),
        "max_participants": 0,
        "status": Event.EventStatus.REGISTRATION_OPEN,
    }
    response = client.post(reverse("events-list"), payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_admin_can_update_foreign_teacher_event(db):
    admin = User.objects.create_user(
        "admin_update_event",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user("teacher_owned", password="securepass123", role=User.UserRole.TEACHER)
    event = Event.objects.create(
        title="Admin edits",
        location="L",
        start_at=timezone.now() + timedelta(days=3),
        registration_deadline=timezone.now() + timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    client = auth_client(admin)
    response = client.patch(
        reverse("events-detail", kwargs={"pk": event.id}),
        {"title": "Patched by admin"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    event.refresh_from_db()
    assert event.title == "Patched by admin"
