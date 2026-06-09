from typing import List

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.registrations.models import Registration
from apps.registrations.serializers import RegistrationSerializer
from apps.registrations.services import create_registration, validate_registration_by_qr
from apps.users.models import User
from apps.users.permissions import IsAdminOrOwnerTeacherEvent, IsAdminOrTeacher, IsStudent

from .models import Event, MandatoryStudent
from .serializers import (
    EventCreateUpdateSerializer,
    EventSerializer,
    MandatoryStudentAttendanceSerializer,
    MandatoryStudentBulkSerializer,
    MandatoryStudentSelfieSerializer,
    MandatoryStudentSerializer,
    RegenerateQRSerializer,
    RegisterByQRSerializer,
)
from .services import (
    add_mandatory_students_to_event,
    generate_unique_qr_token,
    normalize_full_name,
    parse_mandatory_student_names,
    sync_mandatory_selfies_after_event,
)


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
    queryset = Event.objects.select_related("created_by").prefetch_related("mandatory_students")

    def get_queryset(self):
        return Event.objects.select_related("created_by").prefetch_related("mandatory_students")

    def get_permissions(self):
        if self.action in {"list"}:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacher]
        elif self.action in {"create"}:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacher]
        elif self.action in {
            "partial_update",
            "update",
            "destroy",
            "regenerate_qr",
            "mandatory_students",
            "mark_mandatory_attendance",
            "upload_mandatory_selfie",
            "attendance_summary",
        }:
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

    def _extract_mandatory_names_from_validated(self, serializer) -> List[str]:
        lines = serializer.validated_data.pop("mandatory_students_lines", "")
        names = serializer.validated_data.pop("mandatory_students", [])
        return parse_mandatory_student_names(lines=lines, names=names)

    def _serialize_event(self, event):
        event = Event.objects.select_related("created_by").prefetch_related("mandatory_students").get(pk=event.pk)
        return EventSerializer(event, context={"request": self.request}).data

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mandatory_names = self._extract_mandatory_names_from_validated(serializer)
        self.perform_create(serializer)
        event = serializer.instance
        if mandatory_names:
            add_mandatory_students_to_event(event=event, full_names=mandatory_names)
        return Response(self._serialize_event(event), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        mandatory_names = self._extract_mandatory_names_from_validated(serializer)
        self.perform_update(serializer)
        if mandatory_names:
            add_mandatory_students_to_event(event=instance, full_names=mandatory_names)
        instance.refresh_from_db()
        return Response(self._serialize_event(instance), status=status.HTTP_200_OK)

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
        registration = create_registration(
            student=request.user,
            event=event,
            full_name=payload_serializer.validated_data.get("full_name", ""),
            group=payload_serializer.validated_data.get("group", ""),
        )
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

    @extend_schema(
        tags=["Events"],
        request=MandatoryStudentBulkSerializer,
        responses={200: MandatoryStudentSerializer(many=True), 201: MandatoryStudentSerializer(many=True)},
    )
    @action(detail=True, methods=["get", "post"], url_path="mandatory-students")
    def mandatory_students(self, request, pk=None):
        event = self.get_object()
        self.check_object_permissions(request, event)

        if request.method == "GET":
            queryset = event.mandatory_students.all()
            serializer = MandatoryStudentSerializer(queryset, many=True, context={"request": request})
            return Response(serializer.data)

        serializer = MandatoryStudentBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        names = parse_mandatory_student_names(
            lines=serializer.validated_data.get("mandatory_students_lines", ""),
            names=serializer.validated_data.get("mandatory_students", []),
        )
        created, _ = add_mandatory_students_to_event(event=event, full_names=names)
        queryset = event.mandatory_students.all()
        response_serializer = MandatoryStudentSerializer(queryset, many=True, context={"request": request})
        response_status = status.HTTP_201_CREATED if created > 0 else status.HTTP_200_OK
        return Response(response_serializer.data, status=response_status)

    @extend_schema(
        tags=["Events"],
        request=MandatoryStudentAttendanceSerializer,
        responses={200: MandatoryStudentSerializer},
        parameters=[
            OpenApiParameter(
                name="mandatory_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path=r"mandatory-students/(?P<mandatory_id>[^/.]+)/mark-attendance",
    )
    def mark_mandatory_attendance(self, request, pk=None, mandatory_id=None):
        event = self.get_object()
        self.check_object_permissions(request, event)
        mandatory = get_object_or_404(MandatoryStudent, pk=mandatory_id, event=event)

        serializer = MandatoryStudentAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mandatory.attended = serializer.validated_data["attended"]
        mandatory.attendance_marked_at = timezone.now()
        mandatory.save(update_fields=["attended", "attendance_marked_at", "updated_at"])
        return Response(MandatoryStudentSerializer(mandatory, context={"request": request}).data)

    @extend_schema(
        tags=["Events"],
        request=MandatoryStudentSelfieSerializer,
        responses={200: MandatoryStudentSerializer},
        parameters=[
            OpenApiParameter(
                name="mandatory_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path=r"mandatory-students/(?P<mandatory_id>[^/.]+)/upload-selfie",
    )
    @parser_classes([MultiPartParser, FormParser])
    def upload_mandatory_selfie(self, request, pk=None, mandatory_id=None):
        event = self.get_object()
        self.check_object_permissions(request, event)
        mandatory = get_object_or_404(MandatoryStudent, pk=mandatory_id, event=event)

        serializer = MandatoryStudentSelfieSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if mandatory.selfie:
            mandatory.selfie.delete(save=False)
        mandatory.selfie = serializer.validated_data["selfie"]
        mandatory.selfie_uploaded_at = timezone.now()
        mandatory.save(update_fields=["selfie", "selfie_uploaded_at", "updated_at"])
        return Response(MandatoryStudentSerializer(mandatory, context={"request": request}).data)

    @extend_schema(
        tags=["Events"],
        request=None,
        responses={
            200: OpenApiResponse(
                description="Combined attendance summary with mandatory and voluntary participants."
            )
        },
    )
    @action(detail=True, methods=["get"], url_path="attendance-summary")
    def attendance_summary(self, request, pk=None):
        event = self.get_object()
        self.check_object_permissions(request, event)
        sync_mandatory_selfies_after_event(event)

        mandatory_students = list(MandatoryStudent.objects.filter(event=event).order_by("full_name"))
        mandatory_serialized = MandatoryStudentSerializer(
            mandatory_students, many=True, context={"request": request}
        ).data

        confirmed_registrations = (
            Registration.objects.filter(
                event=event,
                attendance_status=Registration.AttendanceStatus.CONFIRMED,
            )
            .select_related("student")
            .order_by("student__last_name", "student__first_name", "student__username")
        )

        actual_participants = []
        registration_name_map = {}
        for registration in confirmed_registrations:
            full_name = normalize_full_name(registration.full_name)
            if not full_name:
                full_name = normalize_full_name(f"{registration.student.last_name} {registration.student.first_name}")
            if not full_name:
                full_name = normalize_full_name(
                    f"{registration.student.first_name} {registration.student.last_name}"
                )
            if not full_name:
                full_name = registration.student.username

            participant_payload = {
                "registration_id": registration.id,
                "student_id": registration.student_id,
                "username": registration.student.username,
                "full_name": full_name,
                "attendance_status": registration.attendance_status,
                "attendance_marked_by_student": registration.attendance_marked_by_student,
                "selfie": registration.selfie.url if registration.selfie else None,
                "confirmed_at": registration.confirmed_at.isoformat() if registration.confirmed_at else None,
            }
            actual_participants.append(participant_payload)
            registration_name_map.setdefault(full_name.casefold(), participant_payload)

        combined_participants = []
        mandatory_names = set()
        for mandatory in mandatory_serialized:
            normalized_name = normalize_full_name(mandatory["full_name"]).casefold()
            mandatory_names.add(normalized_name)
            matched = registration_name_map.get(normalized_name)
            combined_participants.append(
                {
                    "participant_type": "mandatory",
                    "mandatory_student_id": mandatory["id"],
                    "registration_id": matched["registration_id"] if matched else None,
                    "full_name": mandatory["full_name"],
                    "attended": mandatory["attended"],
                    "selfie": mandatory["selfie"] or (matched["selfie"] if matched else None),
                }
            )

        for participant in actual_participants:
            if participant["full_name"].casefold() in mandatory_names:
                continue
            combined_participants.append(
                {
                    "participant_type": "voluntary",
                    "mandatory_student_id": None,
                    "registration_id": participant["registration_id"],
                    "full_name": participant["full_name"],
                    "attended": True,
                    "selfie": participant["selfie"],
                }
            )

        combined_participants.sort(key=lambda item: (item["participant_type"], item["full_name"].casefold()))
        return Response(
            {
                "event_id": event.id,
                "event_title": event.title,
                "mandatory_students": mandatory_serialized,
                "actual_participants": actual_participants,
                "combined_participants": combined_participants,
            }
        )
