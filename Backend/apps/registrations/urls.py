from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EventRegistrationsCSVExportView,
    EventStatsView,
    RatingCSVExportView,
    RatingStatsView,
    RegistrationViewSet,
)


router = DefaultRouter()
router.register(r"registrations", RegistrationViewSet, basename="registrations")

urlpatterns = [
    path("", include(router.urls)),
    path("stats/rating/", RatingStatsView.as_view(), name="stats-rating"),
    path("stats/events/<int:pk>/", EventStatsView.as_view(), name="stats-event"),
    path("exports/rating.csv", RatingCSVExportView.as_view(), name="export-rating"),
    path(
        "exports/event/<int:pk>/registrations.csv",
        EventRegistrationsCSVExportView.as_view(),
        name="export-event-registrations",
    ),
]
