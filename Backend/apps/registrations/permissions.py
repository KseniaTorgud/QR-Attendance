from rest_framework.permissions import BasePermission

from apps.users.models import User


class IsStudentAndOwnRegistration(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.UserRole.STUDENT

    def has_object_permission(self, request, view, obj):
        return obj.student_id == request.user.id


class CanConfirmRegistration(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {
            User.UserRole.ADMIN,
            User.UserRole.TEACHER,
        }

    def has_object_permission(self, request, view, obj):
        if request.user.role == User.UserRole.ADMIN:
            return True
        return obj.event.created_by_id == request.user.id
