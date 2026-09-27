from rest_framework.routers import DefaultRouter

from tasks.views import TaskViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("tasks", TaskViewSet, basename="task")

urlpatterns = router.urls
