from django.urls import path

from customization.views import CustomFieldDetailView, CustomFieldListView, CustomFieldMoveView

urlpatterns = [
    path("custom-fields/", CustomFieldListView.as_view(), name="custom-fields"),
    path("custom-fields/<int:pk>/", CustomFieldDetailView.as_view(), name="custom-field"),
    path("custom-fields/<int:pk>/move/", CustomFieldMoveView.as_view(), name="custom-field-move"),
]
