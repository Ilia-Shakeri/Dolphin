from django.urls import path

from accounts.two_factor_views import (
    LoginTwoFactorView,
    MyRecoveryCodesView,
    MyTwoFactorConfirmView,
    MyTwoFactorDisableView,
    MyTwoFactorSetupView,
    MyTwoFactorView,
)
from accounts.views import LoginView, LogoutView, MeView, MySessionsView


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/sessions/", MySessionsView.as_view(), name="my-sessions"),
    path("login/two-factor/", LoginTwoFactorView.as_view(), name="login-two-factor"),
    path("me/two-factor/", MyTwoFactorView.as_view(), name="my-two-factor"),
    path("me/two-factor/setup/", MyTwoFactorSetupView.as_view(), name="my-two-factor-setup"),
    path("me/two-factor/confirm/", MyTwoFactorConfirmView.as_view(), name="my-two-factor-confirm"),
    path("me/two-factor/disable/", MyTwoFactorDisableView.as_view(), name="my-two-factor-disable"),
    path("me/two-factor/recovery-codes/", MyRecoveryCodesView.as_view(), name="my-two-factor-recovery-codes"),
]

