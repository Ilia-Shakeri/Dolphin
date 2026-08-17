from django.urls import path

from accounts.views import LoginView, LogoutView, MeView, MySessionsView


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/sessions/", MySessionsView.as_view(), name="my-sessions"),
]

