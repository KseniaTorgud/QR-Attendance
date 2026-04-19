from rest_framework import serializers

from .models import Event


class EventSerializer(serializers.ModelSerializer):
    class OwnerSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        username = serializers.CharField()
        role = serializers.CharField()

    created_by = OwnerSerializer(read_only=True)

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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "qr_token", "created_by", "created_at", "updated_at")

class EventCreateUpdateSerializer(serializers.ModelSerializer):
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


class RegisterByQRSerializer(serializers.Serializer):
    qr_token = serializers.CharField(max_length=64)


class RegenerateQRSerializer(serializers.Serializer):
    qr_token = serializers.CharField(read_only=True)
