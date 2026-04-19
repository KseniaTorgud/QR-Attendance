from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


User = get_user_model()


def test_student_registration_sets_default_role(db):
    client = APIClient()
    payload = {
        "username": "new_student",
        "password": "securepass123",
        "first_name": "New",
        "last_name": "Student",
    }

    response = client.post(reverse("auth-register"), payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    user = User.objects.get(username="new_student")
    assert user.role == User.UserRole.STUDENT


def test_student_registration_rejects_short_password(db):
    client = APIClient()
    response = client.post(
        reverse("auth-register"),
        {
            "username": "short_pw_user",
            "password": "short",
            "first_name": "A",
            "last_name": "B",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_student_registration_rejects_duplicate_username(db):
    client = APIClient()
    User.objects.create_user("dup_user", password="securepass123", role=User.UserRole.STUDENT)
    response = client.post(
        reverse("auth-register"),
        {
            "username": "dup_user",
            "password": "anotherpass123",
            "first_name": "X",
            "last_name": "Y",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_login_returns_jwt_tokens(db):
    client = APIClient()
    User.objects.create_user(
        username="student_login",
        password="securepass123",
        role=User.UserRole.STUDENT,
    )

    response = client.post(
        reverse("token-obtain"),
        {"username": "student_login", "password": "securepass123"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data


def test_healthcheck_is_public(db):
    client = APIClient()
    response = client.get(reverse("health"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "ok"


def test_me_requires_authentication(db):
    client = APIClient()
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_with_invalid_password_returns_401(db):
    client = APIClient()
    User.objects.create_user(
        username="student_bad_login",
        password="securepass123",
        role=User.UserRole.STUDENT,
    )
    response = client.post(
        reverse("token-obtain"),
        {"username": "student_bad_login", "password": "wrong-password"},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_token_refresh_returns_new_access(db):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    user = User.objects.create_user(
        username="student_refresh",
        password="securepass123",
        role=User.UserRole.STUDENT,
    )
    refresh = RefreshToken.for_user(user)
    response = client.post(reverse("token-refresh"), {"refresh": str(refresh)}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data


def test_me_returns_current_user(db):
    from rest_framework_simplejwt.tokens import RefreshToken

    user = User.objects.create_user(
        username="student_me",
        password="securepass123",
        role=User.UserRole.STUDENT,
        first_name="Me",
        last_name="User",
    )
    token = str(RefreshToken.for_user(user).access_token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.get(reverse("auth-me"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["username"] == "student_me"
    assert response.data["role"] == User.UserRole.STUDENT
