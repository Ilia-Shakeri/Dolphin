from django.urls import path
from rest_framework.routers import DefaultRouter

from accounts.avatar_views import (
    UserAvatarDefaultChoiceView,
    UserAvatarDefaultsView,
    UserAvatarImageView,
    UserAvatarView,
)
from accounts.views import UserViewSet


router = DefaultRouter()
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    # The account owner's own picture, with no id in the URL. Every role has
    # one of these and nobody needs to know their own primary key to reach
    # it; who may change it is decided in `accounts.avatars` either way.
    path("profile/avatar/", UserAvatarView.as_view(), name="own-avatar"),
    path(
        "profile/avatar/default/",
        UserAvatarDefaultChoiceView.as_view(),
        name="own-avatar-default",
    ),
    path("avatar-defaults/", UserAvatarDefaultsView.as_view(), name="avatar-defaults"),
    path("users/<int:user_id>/avatar/", UserAvatarView.as_view(), name="user-avatar"),
    path(
        "users/<int:user_id>/avatar/default/",
        UserAvatarDefaultChoiceView.as_view(),
        name="user-avatar-default",
    ),
    path(
        "users/<int:user_id>/avatar/image/",
        UserAvatarImageView.as_view(),
        name="user-avatar-image",
    ),
    *router.urls,
]
