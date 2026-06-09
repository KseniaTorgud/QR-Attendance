from rest_framework import serializers

from apps.common.validators import validate_image_file

from .models import Event, MandatoryStudent


class EventSerializer(serializers.ModelSerializer):
    class OwnerSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        username = serializers.CharField()
        role = serializers.CharField()

    created_by = OwnerSerializer(read_only=True)
    mandatory_students_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "description",
            "location",
            "start_at",
            "registration_deadline",
            "max_participants",
            "status",
            "qr_token",
            "created_by",
            "mandatory_students_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "qr_token", "created_by", "created_at", "updated_at")

    def get_mandatory_students_count(self, obj) -> int:
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "mandatory_students" in prefetched:
            return len(prefetched["mandatory_students"])
        return obj.mandatory_students.count()


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    mandatory_students_lines = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="One student full name per line.",
    )
    mandatory_students = serializers.ListField(
        required=False,
        write_only=True,
        child=serializers.CharField(max_length=255),
        help_text="Optional list of student full names.",
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "description",
            "location",
            "start_at",
            "registration_deadline",
            "max_participants",
            "status",
            "mandatory_students_lines",
            "mandatory_students",
        )

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        deadline = attrs.get("registration_deadline", getattr(instance, "registration_deadline", None))
        start_at = attrs.get("start_at", getattr(instance, "start_at", None))
        max_participants = attrs.get("max_participants", getattr(instance, "max_participants", None))

        if deadline and start_at and deadline > start_at:
            raise serializers.ValidationError(
                {"registration_deadline": "Registration deadline must be <= start time."}
            )
        if max_participants is not None and max_participants <= 0:
            raise serializers.ValidationError({"max_participants": "Max participants must be greater than 0."})
        return attrs


class MandatoryStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MandatoryStudent
        fields = (
            "id",
            "event",
            "full_name",
            "attended",
            "attendance_marked_at",
            "selfie",
            "selfie_uploaded_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "event", "attendance_marked_at", "selfie_uploaded_at", "created_at", "updated_at")


class MandatoryStudentBulkSerializer(serializers.Serializer):
    mandatory_students_lines = serializers.CharField(required=False, allow_blank=True)
    mandatory_students = serializers.ListField(
        required=False,
        child=serializers.CharField(max_length=255),
    )

    def validate(self, attrs):
        lines = attrs.get("mandatory_students_lines", "")
        names = attrs.get("mandatory_students", [])
        if not lines and not names:
            raise serializers.ValidationError(
                {"detail": "Provide mandatory_students_lines or mandatory_students."}
            )
        return attrs


class MandatoryStudentAttendanceSerializer(serializers.Serializer):
    attended = serializers.BooleanField()


class MandatoryStudentSelfieSerializer(serializers.Serializer):
    selfie = serializers.ImageField(validators=[validate_image_file])


class RegisterByQRSerializer(serializers.Serializer):
    qr_token = serializers.CharField(max_length=64)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    group = serializers.CharField(max_length=100, required=False, allow_blank=True)


class RegenerateQRSerializer(serializers.Serializer):
    qr_token = serializers.CharField(read_only=True)
