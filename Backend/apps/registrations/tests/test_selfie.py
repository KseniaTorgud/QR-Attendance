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

from apps.events.models import Event
from apps.registrations.models import Registration


User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_image_file(name="selfie.jpg", size=(100, 100), color=(255, 0, 0)):
    file_obj = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(name, file_obj.read(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT="test_media")
def test_student_can_upload_selfie_only_for_own_registration(db):
    teacher = User.objects.create_user("teacher_selfie", password="securepass123", role=User.UserRole.TEACHER)
    student1 = User.objects.create_user("student_selfie_1", password="securepass123", role=User.UserRole.STUDENT)
    student2 = User.objects.create_user("student_selfie_2", password="securepass123", role=User.UserRole.STUDENT)
    event = Event.objects.create(
        title="Selfie event",
        location="Room A",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    own_registration = Registration.objects.create(student=student1, event=event)
    other_registration = Registration.objects.create(student=student2, event=event)
    client = auth_client(student1)

    response_own = client.patch(
        reverse("registrations-upload-selfie", kwargs={"pk": own_registration.id}),
        {"selfie": create_image_file()},
        format="multipart",
    )
    response_other = client.patch(
        reverse("registrations-upload-selfie", kwargs={"pk": other_registration.id}),
        {"selfie": create_image_file(name="other.jpg")},
        format="multipart",
    )

    assert response_own.status_code == status.HTTP_200_OK
    assert response_other.status_code == status.HTTP_404_NOT_FOUND


@override_settings(MEDIA_ROOT="test_media")
def test_non_image_upload_is_rejected(db):
    teacher = User.objects.create_user("teacher_non_image", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_non_image", password="securepass123", role=User.UserRole.STUDENT)
    event = Event.objects.create(
        title="File validation",
        location="Room B",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    registration = Registration.objects.create(student=student, event=event)
    client = auth_client(student)
    file = SimpleUploadedFile("not-image.txt", b"hello world", content_type="text/plain")

    response = client.patch(
        reverse("registrations-upload-selfie", kwargs={"pk": registration.id}),
        {"selfie": file},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@override_settings(MEDIA_ROOT="test_media")
def test_upload_larger_than_size_limit_is_rejected(db):
    teacher = User.objects.create_user("teacher_large", password="securepass123", role=User.UserRole.TEACHER)
    student = User.objects.create_user("student_large", password="securepass123", role=User.UserRole.STUDENT)
    event = Event.objects.create(
        title="Large file",
        location="Room C",
        start_at=timezone.now() + timedelta(days=2),
        registration_deadline=timezone.now() + timedelta(days=1),
        max_participants=10,
        status=Event.EventStatus.REGISTRATION_OPEN,
        created_by=teacher,
    )
    registration = Registration.objects.create(student=student, event=event)
    client = auth_client(student)

    oversized_content = b"x" * (5 * 1024 * 1024 + 1)
    oversized_file = SimpleUploadedFile("big.jpg", oversized_content, content_type="image/jpeg")

    response = client.patch(
        reverse("registrations-upload-selfie", kwargs={"pk": registration.id}),
        {"selfie": oversized_file},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
