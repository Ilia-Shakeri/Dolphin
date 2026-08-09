from rest_framework import viewsets


class NoDestroyModelViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
