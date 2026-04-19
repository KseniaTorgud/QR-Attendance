from django.contrib.auth import get_user_model
from rest_framework import serializers


User = get_user_model()


class SafeUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "date_joined",
        )
        read_only_fields = ("id", "role", "is_active", "date_joined")


class StudentRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "password", "first_name", "last_name", "role")
        read_only_fields = ("id", "role")

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["role"] = User.UserRole.STUDENT
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class TeacherCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "password", "first_name", "last_name", "role", "is_active")
        read_only_fields = ("id", "role")

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["role"] = User.UserRole.TEACHER
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "role", "is_active")

    def validate_role(self, value):
        if value not in User.UserRole.values:
            raise serializers.ValidationError("Invalid role.")
        return value


class SelfUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name")
