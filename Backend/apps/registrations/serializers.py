from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.validators import validate_image_file

from .models import Registration


User = get_user_model()


class RegistrationSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source="student.username", read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)
    confirmed_by_username = serializers.CharField(source="confirmed_by.username", read_only=True)

    class Meta:
        model = Registration
        fields = (
            "id",
            "student",
            "student_username",
            "event",
            "event_title",
            "registered_at",
            "attendance_marked_by_student",
            "attendance_marked_at",
            "selfie",
            "selfie_uploaded_at",
            "attendance_status",
            "confirmed_by",
            "confirmed_by_username",
            "confirmed_at",
            "confirmation_comment",
        )
        read_only_fields = fields


class MarkAttendanceSerializer(serializers.Serializer):
    pass


class SelfieUploadSerializer(serializers.Serializer):
    selfie = serializers.ImageField(validators=[validate_image_file])


class ConfirmRegistrationSerializer(serializers.Serializer):
    attendance_status = serializers.ChoiceField(
        choices=[
            Registration.AttendanceStatus.CONFIRMED,
            Registration.AttendanceStatus.REJECTED,
        ]
    )
    confirmation_comment = serializers.CharField(required=False, allow_blank=True, max_length=255)


class RatingSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    confirmed_visits = serializers.IntegerField()
