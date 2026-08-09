from django.db import connection
from django.db.utils import DatabaseError
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class LivenessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"status": "ok"})


class ReadinessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict, 503: dict})
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            return Response({"status": "unavailable", "database": "down"}, status=503)
        return Response({"status": "ok", "database": "up"})


class HealthView(ReadinessView):
    @extend_schema(exclude=True)
    def get(self, request):
        return super().get(request)
