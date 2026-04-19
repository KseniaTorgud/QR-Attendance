import imghdr
from uuid import uuid4

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = {"jpeg", "png", "gif", "bmp", "webp"}


def validate_image_file(uploaded_file) -> None:
    if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError("Image file is too large. Max size is 5 MB.")

    uploaded_file.seek(0)
    file_header = uploaded_file.read(512)
    uploaded_file.seek(0)
    image_type = imghdr.what(None, h=file_header)
    if image_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError("Only image files are allowed.")

    try:
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
    except (UnidentifiedImageError, OSError, ValidationError):
        raise ValidationError("Invalid image file.")


def selfie_upload_to(instance, filename: str) -> str:
    extension = filename.split(".")[-1].lower() if "." in filename else "jpg"
    return f"selfies/{instance.event_id}/{uuid4().hex}.{extension}"
