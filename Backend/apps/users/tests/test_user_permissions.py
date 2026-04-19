from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


def auth_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_student_cannot_get_users_list(db):
    student = User.objects.create_user(
        username="student1",
        password="securepass123",
        role=User.UserRole.STUDENT,
    )
    client = auth_client(student)

    response = client.get(reverse("users-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_teacher_can_get_users_list_without_passwords(db):
    teacher = User.objects.create_user(
        username="teacher1",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    User.objects.create_user(username="student2", password="securepass123", role=User.UserRole.STUDENT)
    client = auth_client(teacher)

    response = client.get(reverse("users-list"))

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert results
    for item in results:
        assert "password" not in item


def test_teacher_cannot_create_teacher_account(db):
    teacher = User.objects.create_user(
        username="teacher_no_create",
        password="securepass123",
        role=User.UserRole.TEACHER,
    )
    client = auth_client(teacher)
    response = client.post(
        reverse("users-create-teacher"),
        {
            "username": "should_fail",
            "password": "strongpass123",
            "first_name": "N",
            "last_name": "O",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_student_can_view_own_profile(db):
    student = User.objects.create_user(
        username="student_own_profile",
        password="securepass123",
        role=User.UserRole.STUDENT,
    )
    client = auth_client(student)
    response = client.get(reverse("users-detail", kwargs={"pk": student.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["username"] == "student_own_profile"


def test_student_cannot_view_other_student_profile(db):
    s1 = User.objects.create_user("student_a", password="securepass123", role=User.UserRole.STUDENT)
    s2 = User.objects.create_user("student_b", password="securepass123", role=User.UserRole.STUDENT)
    client = auth_client(s1)
    response = client.get(reverse("users-detail", kwargs={"pk": s2.id}))
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_student_can_patch_own_profile(db):
    student = User.objects.create_user(
        "student_patch_self",
        password="securepass123",
        role=User.UserRole.STUDENT,
        first_name="Old",
        last_name="Name",
    )
    client = auth_client(student)
    response = client.patch(
        reverse("users-detail", kwargs={"pk": student.id}),
        {"first_name": "New"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    student.refresh_from_db()
    assert student.first_name == "New"


def test_student_cannot_patch_other_profile(db):
    s1 = User.objects.create_user("student_patch_a", password="securepass123", role=User.UserRole.STUDENT)
    s2 = User.objects.create_user("student_patch_b", password="securepass123", role=User.UserRole.STUDENT)
    client = auth_client(s1)
    response = client.patch(
        reverse("users-detail", kwargs={"pk": s2.id}),
        {"first_name": "Hacker"},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_admin_can_patch_another_user(db):
    admin = User.objects.create_user(
        "admin_patch_user",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    target = User.objects.create_user(
        "target_user",
        password="securepass123",
        role=User.UserRole.STUDENT,
        first_name="T",
        last_name="U",
    )
    client = auth_client(admin)
    response = client.patch(
        reverse("users-detail", kwargs={"pk": target.id}),
        {"first_name": "UpdatedByAdmin"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    target.refresh_from_db()
    assert target.first_name == "UpdatedByAdmin"


def test_admin_can_create_teacher(db):
    admin = User.objects.create_user(
        username="admin1",
        password="securepass123",
        role=User.UserRole.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    client = auth_client(admin)
    payload = {
        "username": "created_teacher",
        "password": "strongpass123",
        "first_name": "Teacher",
        "last_name": "One",
    }

    response = client.post(reverse("users-create-teacher"), payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    teacher = User.objects.get(username="created_teacher")
    assert teacher.role == User.UserRole.TEACHER
