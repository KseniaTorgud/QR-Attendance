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


def create_event(owner, title):
    return Event.objects.create(
        title=title,
        location="Room Stats",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=20,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=owner,
    )


def test_rating_counts_only_confirmed(db):
    admin = User.objects.create_user(
        "admin_stats",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user("teacher_stats", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_stats", password="securepass123", role=User.UserRole.STUDENT)
    event1 = create_event(teacher, "Event 1")
    event2 = create_event(teacher, "Event 2")

    Registration.objects.create(
        student=student,
        event=event1,
        attendance_status=Registration.AttendanceStatus.CONFIRMED,
    )
    Registration.objects.create(
        student=student,
        event=event2,
        attendance_status=Registration.AttendanceStatus.REJECTED,
    )
    client = auth_client(admin)

    response = client.get(reverse("stats-rating"))

    assert response.status_code == status.HTTP_200_OK
    student_row = next(item for item in response.data if item["username"] == "student_stats")
    assert student_row["confirmed_visits"] == 1


def test_csv_exports_have_role_protection(db):
    admin = User.objects.create_user(
        "admin_export",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user("teacher_export", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_export", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher, "Export event")
    Registration.objects.create(
        student=student,
        event=event,
        attendance_status=Registration.AttendanceStatus.PENDING,
    )

    admin_client = auth_client(admin)
    student_client = auth_client(student)
    teacher_client = auth_client(teacher)

    admin_rating_response = admin_client.get(reverse("export-rating"))
    student_rating_response = student_client.get(reverse("export-rating"))
    teacher_event_export_response = teacher_client.get(
        reverse("export-event-registrations", kwargs={"pk": event.id})
    )

    assert admin_rating_response.status_code == status.HTTP_200_OK
    assert admin_rating_response["Content-Type"].startswith("text/csv")
    assert student_rating_response.status_code == status.HTTP_403_FORBIDDEN
    assert teacher_event_export_response.status_code == status.HTTP_200_OK
    assert teacher_event_export_response["Content-Type"].startswith("text/csv")


def test_admin_event_stats_returns_counts(db):
    admin = User.objects.create_user(
        "admin_ev_stats",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user("t_ev_stats", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_ev_stats", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher, "Stats event")
    Registration.objects.create(
        student=student,
        event=event,
        attendance_status=Registration.AttendanceStatus.CONFIRMED,
    )
    Registration.objects.create(
        student=User.objects.create_user("s_ev2", password="securepass123", role=User.UserRole.STUDENT),
        event=event,
        attendance_status=Registration.AttendanceStatus.PENDING,
    )
    client = auth_client(admin)
    response = client.get(reverse("stats-event", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_registrations"] == 2
    assert response.data["total_confirmed"] == 1
    assert response.data["total_pending"] == 1
    assert response.data["free_slots"] == event.max_participants - 2


def test_teacher_can_view_own_event_stats(db):
    teacher = User.objects.create_user("t_own_stats", password="securepass123", role=User.UserRole.TEACHER)
    event = create_event(teacher, "Own stats")
    client = auth_client(teacher)
    response = client.get(reverse("stats-event", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_registrations"] == 0


def test_teacher_cannot_view_foreign_event_stats(db):
    owner = User.objects.create_user("t_stat_own", password="securepass123", role=User.UserRole.TEACHER)
    foreign = User.objects.create_user("t_stat_for", password="securepass123", role=User.UserRole.TEACHER)
    event = create_event(owner, "Not yours")
    client = auth_client(foreign)
    response = client.get(reverse("stats-event", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_student_cannot_view_event_stats(db):
    teacher = User.objects.create_user("t_st_stats", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_st_stats", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher, "Student stats")
    client = auth_client(student)
    response = client.get(reverse("stats-event", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_teacher_cannot_export_foreign_event_csv(db):
    owner = User.objects.create_user("t_exp_own", password="securepass123", role=User.UserRole.TEACHER)
    foreign = User.objects.create_user("t_exp_for", password="securepass123", role=User.UserRole.TEACHER)
    event = create_event(owner, "Export block")
    client = auth_client(foreign)
    response = client.get(reverse("export-event-registrations", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_can_export_any_event_csv(db):
    admin = User.objects.create_user(
        "admin_export_ev",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    teacher = User.objects.create_user("t_adm_exp", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_adm_exp", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher, "Admin export")
    Registration.objects.create(student=student, event=event)
    client = auth_client(admin)
    response = client.get(reverse("export-event-registrations", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"].startswith("text/csv")
    assert str(event.id).encode() in response.content or b"registration_id" in response.content


def test_student_cannot_export_event_csv(db):
    teacher = User.objects.create_user("t_st_exp", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_st_exp", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher, "No export")
    client = auth_client(student)
    response = client.get(reverse("export-event-registrations", kwargs={"pk": event.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_student_cannot_export_rating_csv(db):
    student = User.objects.create_user("s_rate_exp", password="securepass123", role=User.UserRole.STUDENT)
    client = auth_client(student)
    response = client.get(reverse("export-rating"))
    assert response.status_code == status.HTTP_403_FORBIDDEN
