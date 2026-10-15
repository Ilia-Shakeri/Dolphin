from django.urls import path

from customization.views import (
    CustomFieldDetailView,
    CustomFieldListView,
    CustomFieldMoveView,
    SavedViewDetailView,
    SavedViewListView,
)

urlpatterns = [
    path("custom-fields/", CustomFieldListView.as_view(), name="custom-fields"),
    path("custom-fields/<int:pk>/", CustomFieldDetailView.as_view(), name="custom-field"),
    path("custom-fields/<int:pk>/move/", CustomFieldMoveView.as_view(), name="custom-field-move"),
    path("saved-views/", SavedViewListView.as_view(), name="saved-views"),
    path("saved-views/<int:pk>/", SavedViewDetailView.as_view(), name="saved-view"),
]
