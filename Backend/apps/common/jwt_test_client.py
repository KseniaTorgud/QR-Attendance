from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class JwtAuthorizedApiClientFactory:
    """Builds an APIClient authenticated as the given user (Bearer access token)."""

    @staticmethod
    def create_for_user(user) -> APIClient:
        client = APIClient()
        token = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client
