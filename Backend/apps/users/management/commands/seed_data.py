from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


User = get_user_model()


class Command(BaseCommand):
    help = "Create default admin/teacher/student users for demo and frontend integration."

    def handle(self, *args, **options):
        users_to_create = [
            {
                "username": "admin",
                "password": "admin12345",
                "role": User.UserRole.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "first_name": "System",
                "last_name": "Admin",
            },
            {
                "username": "teacher",
                "password": "teacher12345",
                "role": User.UserRole.TEACHER,
                "first_name": "Default",
                "last_name": "Teacher",
            },
            {
                "username": "student",
                "password": "student12345",
                "role": User.UserRole.STUDENT,
                "first_name": "Default",
                "last_name": "Student",
            },
        ]

        for payload in users_to_create:
            username = payload.pop("username")
            password = payload.pop("password")
            user, created = User.objects.get_or_create(username=username, defaults=payload)
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(self.style.SUCCESS(f"Created {username}"))
            else:
                changed = False
                for field, value in payload.items():
                    if getattr(user, field) != value:
                        setattr(user, field, value)
                        changed = True
                if changed:
                    user.save()
                self.stdout.write(f"{username} already exists, skipped")
