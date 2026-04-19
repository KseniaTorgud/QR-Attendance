from rest_framework.permissions import BasePermission

from apps.users.models import User


class CanManageEvent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {
            User.UserRole.ADMIN,
            User.UserRole.TEACHER,
        }

    def has_object_permission(self, request, view, obj):
        if request.user.role == User.UserRole.ADMIN:
            return True
        return request.user.role == User.UserRole.TEACHER and obj.created_by_id == request.user.id
