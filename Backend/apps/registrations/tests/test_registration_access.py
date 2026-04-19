from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.common.jwt_test_client import JwtAuthorizedApiClientFactory
from apps.events.models import Event
from apps.registrations.models import Registration


User = get_user_model()


def create_event(teacher, title="Ev"):
    now = timezone.now()
    return Event.objects.create(
        title=title,
        location="L",
        start_at=now + timedelta(days=2),
        registration_deadline=now + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )


def test_student_can_mark_attendance_on_own_registration(db):
    teacher = User.objects.create_user("t_mark", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_mark", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher)
    registration = Registration.objects.create(student=student, event=event)
    client = JwtAuthorizedApiClientFactory.create_for_user(student)
    response = client.patch(reverse("registrations-mark-attendance", kwargs={"pk": registration.id}), {}, format="json")
    assert response.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.attendance_marked_by_student is True
    assert registration.attendance_marked_at is not None


def test_student_cannot_mark_attendance_for_other_registration(db):
    teacher = User.objects.create_user("t_mark2", password="securepass123", role=User.UserRole.TEACHER)
    s1 = User.objects.create_user("s_mark1", password="securepass123", role=User.UserRole.STUDENT)
    s2 = User.objects.create_user("s_mark2", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher)
    other = Registration.objects.create(student=s2, event=event)
    client = JwtAuthorizedApiClientFactory.create_for_user(s1)
    response = client.patch(reverse("registrations-mark-attendance", kwargs={"pk": other.id}), {}, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_student_cannot_confirm_registration(db):
    teacher = User.objects.create_user("t_conf_s", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_conf", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher)
    registration = Registration.objects.create(student=student, event=event)
    client = JwtAuthorizedApiClientFactory.create_for_user(student)
    response = client.patch(
        reverse("registrations-confirm", kwargs={"pk": registration.id}),
        {"attendance_status": Registration.AttendanceStatus.CONFIRMED},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_teacher_registration_list_scoped_to_own_events(db):
    t1 = User.objects.create_user("t_scope1", password="securepass123", role=User.UserRole.TEACHER)
    t2 = User.objects.create_user("t_scope2", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_scope", password="securepass123", role=User.UserRole.STUDENT)
    e1 = create_event(t1, title="Mine")
    e2 = create_event(t2, title="Foreign")
    Registration.objects.create(student=student, event=e1)
    Registration.objects.create(student=student, event=e2)
    client = JwtAuthorizedApiClientFactory.create_for_user(t1)
    response = client.get(reverse("registrations-list"))
    assert response.status_code == status.HTTP_200_OK
    titles = {row["event_title"] for row in response.data["results"]}
    assert titles == {"Mine"}


def test_student_registration_list_only_self(db):
    teacher = User.objects.create_user("t_stu_list", password="securepass123", role=User.UserRole.TEACHER)
    s1 = User.objects.create_user("s_list1", password="securepass123", role=User.UserRole.STUDENT)
    s2 = User.objects.create_user("s_list2", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher, title="Shared event")
    Registration.objects.create(student=s1, event=event)
    Registration.objects.create(student=s2, event=event)
    client = JwtAuthorizedApiClientFactory.create_for_user(s1)
    response = client.get(reverse("registrations-list"))
    assert response.status_code == status.HTTP_200_OK
    usernames = {row["student_username"] for row in response.data["results"]}
    assert usernames == {"s_list1"}


def test_admin_sees_all_registrations_in_list(db):
    admin = User.objects.create_user(
        "admin_reg_list",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    t1 = User.objects.create_user("t_adm1", password="securepass123", role=User.UserRole.TEACHER)
    t2 = User.objects.create_user("t_adm2", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("s_adm", password="securepass123", role=User.UserRole.STUDENT)
    Registration.objects.create(student=student, event=create_event(t1, title="A"))
    Registration.objects.create(student=student, event=create_event(t2, title="B"))
    client = JwtAuthorizedApiClientFactory.create_for_user(admin)
    response = client.get(reverse("registrations-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) >= 2


def test_student_cannot_retrieve_foreign_registration(db):
    teacher = User.objects.create_user("t_ret", password="securepass123", role=User.UserRole.TEACHER)
    s1 = User.objects.create_user("s_ret1", password="securepass123", role=User.UserRole.STUDENT)
    s2 = User.objects.create_user("s_ret2", password="securepass123", role=User.UserRole.STUDENT)
    event = create_event(teacher)
    reg_other = Registration.objects.create(student=s2, event=event)
    client = JwtAuthorizedApiClientFactory.create_for_user(s1)
    response = client.get(reverse("registrations-detail", kwargs={"pk": reg_other.id}))
    assert response.status_code == status.HTTP_404_NOT_FOUND
