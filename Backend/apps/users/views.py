from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdmin, IsAdminOrTeacher
from .serializers import (
    AdminUserUpdateSerializer,
    SafeUserSerializer,
    SelfUserUpdateSerializer,
    StudentRegistrationSerializer,
    TeacherCreateSerializer,
)


User = get_user_model()


@extend_schema(
    tags=["Auth"],
    request=StudentRegistrationSerializer,
    responses={201: SafeUserSerializer},
    examples=[
        OpenApiExample(
            "Student registration request",
            value={
                "username": "student1",
                "password": "strongpass123",
                "first_name": "Ivan",
                "last_name": "Petrov",
            },
            request_only=True,
        ),
    ],
)
class RegisterStudentView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = StudentRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(SafeUserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Auth"],
    responses={200: SafeUserSerializer},
)
class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(SafeUserSerializer(request.user).data)


@extend_schema_view(
    list=extend_schema(tags=["Users"], responses={200: SafeUserSerializer(many=True)}),
    retrieve=extend_schema(tags=["Users"], responses={200: SafeUserSerializer}),
    partial_update=extend_schema(
        tags=["Users"],
        request=AdminUserUpdateSerializer,
        responses={200: SafeUserSerializer},
    ),
)
class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.all().order_by("id")

    def get_permissions(self):
        if self.action == "list":
            permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacher]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role in {User.UserRole.ADMIN, User.UserRole.TEACHER}:
            return User.objects.all().order_by("id")
        return User.objects.filter(id=user.id)

    def get_serializer_class(self):
        if self.action == "partial_update":
            if self.request.user.role == User.UserRole.ADMIN:
                return AdminUserUpdateSerializer
            return SelfUserUpdateSerializer
        return SafeUserSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.role == User.UserRole.STUDENT and request.user.id != instance.id:
            return Response({"detail": "You can view only your own profile."}, status=status.HTTP_403_FORBIDDEN)
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_admin = request.user.role == User.UserRole.ADMIN
        if not is_admin and request.user.id != instance.id:
            return Response({"detail": "You can edit only your own profile."}, status=status.HTTP_403_FORBIDDEN)
        response = super().partial_update(request, *args, **kwargs)
        response.data = SafeUserSerializer(self.get_object()).data
        return response


@extend_schema(
    tags=["Users"],
    request=TeacherCreateSerializer,
    responses={
        201: SafeUserSerializer,
        403: OpenApiResponse(description="Only admin can create teacher accounts."),
    },
)
class TeacherCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        serializer = TeacherCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        teacher = serializer.save()
        return Response(SafeUserSerializer(teacher).data, status=status.HTTP_201_CREATED)


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def healthcheck(_request):
    return Response({"status": "ok"})
