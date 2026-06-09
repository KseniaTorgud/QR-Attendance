import csv

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.models import Event
from apps.users.models import User
from apps.users.permissions import IsAdmin

from .models import Registration
from .permissions import CanConfirmRegistration, IsStudentAndOwnRegistration
from .serializers import (
    ConfirmRegistrationSerializer,
    MarkAttendanceSerializer,
    RatingSerializer,
    RegistrationSerializer,
    SelfieUploadSerializer,
)


AppUser = get_user_model()


@extend_schema_view(
    list=extend_schema(tags=["Registrations"], responses={200: RegistrationSerializer(many=True)}),
    retrieve=extend_schema(tags=["Registrations"], responses={200: RegistrationSerializer}),
)
class RegistrationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RegistrationSerializer
    queryset = Registration.objects.select_related("student", "event", "confirmed_by", "event__created_by")

    def get_permissions(self):
        if self.action in {"mark_attendance", "upload_selfie"}:
            permission_classes = [permissions.IsAuthenticated, IsStudentAndOwnRegistration]
        elif self.action == "confirm":
            permission_classes = [permissions.IsAuthenticated, CanConfirmRegistration]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        base_qs = Registration.objects.select_related("student", "event", "confirmed_by", "event__created_by")
        if user.role == User.UserRole.ADMIN:
            return base_qs
        if user.role == User.UserRole.TEACHER:
            return base_qs.filter(event__created_by=user)
        return base_qs.filter(student=user)

    @extend_schema(
        tags=["Registrations"],
        request=MarkAttendanceSerializer,
        responses={200: RegistrationSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="mark-attendance")
    def mark_attendance(self, request, pk=None):
        registration = self.get_object()
        self.check_object_permissions(request, registration)
        registration.attendance_marked_by_student = True
        registration.attendance_marked_at = timezone.now()
        registration.save(update_fields=["attendance_marked_by_student", "attendance_marked_at"])
        return Response(RegistrationSerializer(registration).data)

    @extend_schema(
        tags=["Registrations"],
        request=SelfieUploadSerializer,
        responses={
            200: RegistrationSerializer,
            400: OpenApiResponse(description="Invalid image or file too large."),
        },
        examples=[
            OpenApiExample(
                "Selfie upload",
                summary="Multipart form-data example",
                value={"selfie": "<binary image>"},
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["patch"], url_path="upload-selfie")
    @parser_classes([MultiPartParser, FormParser])
    def upload_selfie(self, request, pk=None):
        registration = self.get_object()
        self.check_object_permissions(request, registration)

        serializer = SelfieUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if registration.selfie:
            registration.selfie.delete(save=False)
        registration.selfie = serializer.validated_data["selfie"]
        registration.selfie_uploaded_at = timezone.now()
        registration.save(update_fields=["selfie", "selfie_uploaded_at"])
        return Response(RegistrationSerializer(registration).data)

    @extend_schema(
        tags=["Registrations"],
        request=ConfirmRegistrationSerializer,
        responses={200: RegistrationSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="confirm")
    def confirm(self, request, pk=None):
        registration = self.get_object()
        self.check_object_permissions(request, registration)

        serializer = ConfirmRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration.attendance_status = serializer.validated_data["attendance_status"]
        registration.confirmation_comment = serializer.validated_data.get("confirmation_comment", "")
        registration.confirmed_by = request.user
        registration.confirmed_at = timezone.now()
        registration.save(
            update_fields=["attendance_status", "confirmation_comment", "confirmed_by", "confirmed_at"]
        )
        return Response(RegistrationSerializer(registration).data)


@extend_schema(
    tags=["Statistics"],
    responses={200: RatingSerializer(many=True)},
)
class RatingStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        queryset = (
            AppUser.objects.filter(role=User.UserRole.STUDENT)
            .annotate(
                confirmed_visits=Count(
                    "registrations",
                    filter=Q(registrations__attendance_status=Registration.AttendanceStatus.CONFIRMED),
                )
            )
            .order_by("-confirmed_visits", "username")
        )
        payload = [
            {
                "student_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "confirmed_visits": user.confirmed_visits,
            }
            for user in queryset
        ]
        return Response(payload)


@extend_schema(
    tags=["Statistics"],
    responses={
        200: OpenApiResponse(
            description="Event stats",
            response={
                "type": "object",
                "properties": {
                    "total_registrations": {"type": "integer"},
                    "total_confirmed": {"type": "integer"},
                    "total_rejected": {"type": "integer"},
                    "total_pending": {"type": "integer"},
                    "free_slots": {"type": "integer"},
                },
            },
        )
    },
)
class EventStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        event = get_object_or_404(Event, pk=pk)
        if request.user.role == User.UserRole.TEACHER and event.created_by_id != request.user.id:
            return Response({"detail": "You can access only your own events."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == User.UserRole.STUDENT:
            return Response({"detail": "You do not have permission to view stats."}, status=status.HTTP_403_FORBIDDEN)

        event_regs = Registration.objects.filter(event=event)
        total_registrations = event_regs.count()
        total_confirmed = event_regs.filter(attendance_status=Registration.AttendanceStatus.CONFIRMED).count()
        total_rejected = event_regs.filter(attendance_status=Registration.AttendanceStatus.REJECTED).count()
        total_pending = event_regs.filter(attendance_status=Registration.AttendanceStatus.PENDING).count()
        return Response(
            {
                "total_registrations": total_registrations,
                "total_confirmed": total_confirmed,
                "total_rejected": total_rejected,
                "total_pending": total_pending,
                "free_slots": max(event.max_participants - total_registrations, 0),
            }
        )


@extend_schema(
    tags=["Exports"],
    responses={200: OpenApiResponse(description="CSV file")},
)
class RatingCSVExportView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        queryset = (
            AppUser.objects.filter(role=User.UserRole.STUDENT)
            .annotate(
                confirmed_visits=Count(
                    "registrations",
                    filter=Q(registrations__attendance_status=Registration.AttendanceStatus.CONFIRMED),
                )
            )
            .order_by("-confirmed_visits", "username")
        )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="rating.csv"'
        writer = csv.writer(response)
        writer.writerow(["student_id", "username", "first_name", "last_name", "confirmed_visits"])
        for student in queryset:
            writer.writerow(
                [
                    student.id,
                    student.username,
                    student.first_name,
                    student.last_name,
                    student.confirmed_visits,
                ]
            )
        return response


@extend_schema(
    tags=["Exports"],
    responses={200: OpenApiResponse(description="CSV file")},
)
class EventRegistrationsCSVExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        event = get_object_or_404(Event, pk=pk)
        if request.user.role == User.UserRole.TEACHER and event.created_by_id != request.user.id:
            return Response({"detail": "You can export only your own events."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == User.UserRole.STUDENT:
            return Response({"detail": "You do not have permission to export data."}, status=status.HTTP_403_FORBIDDEN)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="event_{event.id}_registrations.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "registration_id",
                "student_id",
                "username",
                "first_name",
                "last_name",
                "attendance_marked_by_student",
                "attendance_status",
                "confirmed_by",
                "confirmation_comment",
                "registered_at",
            ]
        )
        for registration in Registration.objects.filter(event=event).select_related("student", "confirmed_by"):
            writer.writerow(
                [
                    registration.id,
                    registration.student_id,
                    registration.student.username,
                    registration.student.first_name,
                    registration.student.last_name,
                    registration.attendance_marked_by_student,
                    registration.attendance_status,
                    registration.confirmed_by.username if registration.confirmed_by else "",
                    registration.confirmation_comment,
                    registration.registered_at.isoformat(),
                ]
            )
        return response
