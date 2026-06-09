from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import MeView, RegisterStudentView, TeacherCreateView, UserViewSet, healthcheck


router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")

urlpatterns = [
    path("health/", healthcheck, name="health"),
    path("auth/register/", RegisterStudentView.as_view(), name="auth-register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("users/teachers/", TeacherCreateView.as_view(), name="users-create-teacher"),
    path("", include(router.urls)),
]
