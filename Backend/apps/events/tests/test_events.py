from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.events.models import Event, MandatoryStudent
from apps.registrations.models import Registration


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


def create_image_file(name="selfie.jpg", size=(100, 100), color=(0, 255, 0)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(name, file_obj.read(), content_type="image/jpeg")


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


def test_create_event_with_mandatory_students_lines(db):
    teacher = User.objects.create_user("teacher_mandatory", password="securepass123", role=User.UserRole.TEACHER)
    client = auth_client(teacher)
    payload = event_payload()
    payload["mandatory_students_lines"] = "Ivan Petrov\nMaria Sidorova\nIvan Petrov"

    response = client.post(reverse("events-list"), payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    event = Event.objects.get(pk=response.data["id"])
    full_names = list(event.mandatory_students.values_list("full_name", flat=True))
    assert full_names == ["Ivan Petrov", "Maria Sidorova"]


def test_mandatory_students_visible_only_for_owner_or_admin(db):
    owner = User.objects.create_user("owner_mandatory", password="securepass123", role=User.UserRole.TEACHER)
    foreign_teacher = User.objects.create_user(
        "foreign_mandatory",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    admin = User.objects.create_user(
        "admin_mandatory",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    student = User.objects.create_user("student_mandatory", password="securepass123", role=User.UserRole.STUDENT)
    event = Event.objects.create(
        title="Mandatory visibility",
        location="L",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=owner,
    )
    MandatoryStudent.objects.create(event=event, full_name="Alice Cooper")

    owner_response = auth_client(owner).get(reverse("events-mandatory-students", kwargs={"pk": event.id}))
    admin_response = auth_client(admin).get(reverse("events-mandatory-students", kwargs={"pk": event.id}))
    foreign_response = auth_client(foreign_teacher).get(reverse("events-mandatory-students", kwargs={"pk": event.id}))
    student_response = auth_client(student).get(reverse("events-mandatory-students", kwargs={"pk": event.id}))

    assert owner_response.status_code == status.HTTP_200_OK
    assert admin_response.status_code == status.HTTP_200_OK
    assert foreign_response.status_code == status.HTTP_403_FORBIDDEN
    assert student_response.status_code == status.HTTP_403_FORBIDDEN


@override_settings(MEDIA_ROOT="test_media")
def test_owner_can_mark_mandatory_attendance_and_upload_selfie(db):
    teacher = User.objects.create_user("teacher_mark", password="securepass123", role=User.UserRole.TEACHER)
    event = Event.objects.create(
        title="Mandatory mark",
        location="L",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    mandatory = MandatoryStudent.objects.create(event=event, full_name="Bob Martin")
    client = auth_client(teacher)

    mark_response = client.patch(
        reverse(
            "events-mark-mandatory-attendance",
            kwargs={"pk": event.id, "mandatory_id": mandatory.id},
        ),
        {"attended": True},
        format="json",
    )
    selfie_response = client.patch(
        reverse(
            "events-upload-mandatory-selfie",
            kwargs={"pk": event.id, "mandatory_id": mandatory.id},
        ),
        {"selfie": create_image_file()},
        format="multipart",
    )

    assert mark_response.status_code == status.HTTP_200_OK
    assert selfie_response.status_code == status.HTTP_200_OK
    mandatory.refresh_from_db()
    assert mandatory.attended is True
    assert mandatory.selfie


@override_settings(MEDIA_ROOT="test_media")
def test_attendance_summary_contains_mandatory_and_voluntary(db):
    teacher = User.objects.create_user("teacher_summary", password="securepass123", role=User.UserRole.TEACHER)
    student_mandatory = User.objects.create_user(
        "student_mandatory_summary",
        password="securepass123",
        role=User.UserRole.STUDENT,
        first_name="Ivan",
        last_name="Petrov",
    )
    student_voluntary = User.objects.create_user(
        "student_voluntary_summary",
        password="securepass123",
        role=User.UserRole.STUDENT,
        first_name="Pavel",
        last_name="Smirnov",
    )
    event = Event.objects.create(
        title="Summary event",
        location="L",
        start_at=timezone.now() - timedelta(days=1),
        registration_deadline=timezone.now() - timedelta(days=2),
        max_participants=10,
        status=Event.EventStatus.FINISHED,
        created_by=teacher,
    )
    MandatoryStudent.objects.create(event=event, full_name="Petrov Ivan")
    MandatoryStudent.objects.create(event=event, full_name="Obligatory Student")

    Registration.objects.create(
        student=student_mandatory,
        event=event,
        attendance_status=Registration.AttendanceStatus.CONFIRMED,
        selfie=create_image_file(name="mandatory.jpg"),
    )
    Registration.objects.create(
        student=student_voluntary,
        event=event,
        attendance_status=Registration.AttendanceStatus.CONFIRMED,
        selfie=create_image_file(name="voluntary.jpg"),
    )
    client = auth_client(teacher)

    response = client.get(reverse("events-attendance-summary", kwargs={"pk": event.id}))

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["mandatory_students"]) == 2
    assert len(response.data["actual_participants"]) == 2
    participant_types = {row["participant_type"] for row in response.data["combined_participants"]}
    assert participant_types == {"mandatory", "voluntary"}
