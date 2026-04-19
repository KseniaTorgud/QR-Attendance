from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.registrations.serializers import RegistrationSerializer
from apps.registrations.services import create_registration, validate_registration_by_qr
from apps.users.models import User
from apps.users.permissions import IsAdminOrOwnerTeacherEvent, IsAdminOrTeacher, IsStudent

from .models import Event
from .serializers import EventCreateUpdateSerializer, EventSerializer, RegenerateQRSerializer, RegisterByQRSerializer
from .services import generate_unique_qr_token


@extend_schema_view(
    list=extend_schema(tags=["Events"], responses={200: EventSerializer(many=True)}),
    retrieve=extend_schema(tags=["Events"], responses={200: EventSerializer}),
    create=extend_schema(tags=["Events"], request=EventCreateUpdateSerializer, responses={201: EventSerializer}),
    partial_update=extend_schema(
        tags=["Events"],
        request=EventCreateUpdateSerializer,
        responses={200: EventSerializer},
    ),
    destroy=extend_schema(tags=["Events"], responses={204: OpenApiResponse(description="Deleted")}),
)
class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.select_related("created_by").all()

    def get_permissions(self):
        if self.action in {"list"}:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacher]
        elif self.action in {"create"}:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacher]
        elif self.action in {"partial_update", "update", "destroy", "regenerate_qr"}:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerTeacherEvent]
        elif self.action == "register_by_qr":
            permission_classes = [permissions.IsAuthenticated, IsStudent]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action in {"create", "partial_update", "update"}:
            return EventCreateUpdateSerializer
        return EventSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if request.user.role == User.UserRole.TEACHER and request.query_params.get("mine") == "true":
            queryset = queryset.filter(created_by=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = EventSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventSerializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        event = Event.objects.select_related("created_by").get(pk=serializer.instance.pk)
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        return Response(EventSerializer(instance).data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Events"],
        request=RegisterByQRSerializer,
        responses={
            201: RegistrationSerializer,
            400: OpenApiResponse(description="Validation error."),
            409: OpenApiResponse(description="Conflict."),
        },
        examples=[
            OpenApiExample(
                "Register by QR",
                value={"qr_token": "sample_qr_token"},
                request_only=True,
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="register-by-qr")
    def register_by_qr(self, request, pk=None):
        event = self.get_object()
        payload_serializer = RegisterByQRSerializer(data=request.data)
        payload_serializer.is_valid(raise_exception=True)

        validate_registration_by_qr(
            student=request.user,
            event=event,
            qr_token=payload_serializer.validated_data["qr_token"],
        )
        registration = create_registration(student=request.user, event=event)
        return Response(RegistrationSerializer(registration).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Events"],
        request=None,
        responses={200: RegenerateQRSerializer},
    )
    @action(detail=True, methods=["post"], url_path="regenerate-qr")
    def regenerate_qr(self, request, pk=None):
        event = self.get_object()
        self.check_object_permissions(request, event)
        event.qr_token = generate_unique_qr_token()
        event.save(update_fields=["qr_token", "updated_at"])
        return Response({"qr_token": event.qr_token}, status=status.HTTP_200_OK)
