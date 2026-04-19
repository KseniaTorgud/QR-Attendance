import secrets


def generate_unique_qr_token() -> str:
    from .models import Event

    while True:
        token = secrets.token_urlsafe(32)
        if not Event.objects.filter(qr_token=token).exists():
            return token
