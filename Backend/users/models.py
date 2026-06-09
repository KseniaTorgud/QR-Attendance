from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class AppUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.UserRole.ADMIN)
        return super().create_superuser(username, email=email, password=password, **extra_fields)


class User(AbstractUser):
    class UserRole(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    id = models.BigAutoField(primary_key=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STUDENT)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = AppUserManager()

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"
