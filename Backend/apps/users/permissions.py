from rest_framework.permissions import BasePermission

from .models import User


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.UserRole.ADMIN


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.UserRole.TEACHER


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.UserRole.STUDENT


class IsAdminOrTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {
            User.UserRole.ADMIN,
            User.UserRole.TEACHER,
        }


class IsAdminOrOwnerTeacherEvent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {
            User.UserRole.ADMIN,
            User.UserRole.TEACHER,
        }

    def has_object_permission(self, request, view, obj):
        if request.user.role == User.UserRole.ADMIN:
            return True
        return request.user.role == User.UserRole.TEACHER and obj.created_by_id == request.user.id


class IsStudentAndOwnProfile(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.UserRole.STUDENT

    def has_object_permission(self, request, view, obj):
        return request.user.id == obj.id
