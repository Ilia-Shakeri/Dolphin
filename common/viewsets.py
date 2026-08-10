from rest_framework import viewsets
from rest_framework.exceptions import ValidationError


class StrictQueryParametersMixin:
    common_list_query_parameters = {"format", "ordering", "page", "search"}
    list_query_parameters = set()
    action_query_parameters = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in {"GET", "HEAD"}:
            return
        action_name = getattr(self, "action", None)
        allowed = {"format"} | set(self.action_query_parameters.get(action_name, set()))
        if action_name == "list":
            allowed |= self.common_list_query_parameters | set(self.list_query_parameters)
        errors = {
            name: ["Unknown query parameter."]
            for name in sorted(set(request.query_params) - allowed)
        }
        for name in sorted(set(request.query_params) & allowed):
            if len(request.query_params.getlist(name)) > 1:
                errors[name] = ["Query parameter must appear once."]
        if errors:
            raise ValidationError(errors)


class NoDestroyModelViewSet(StrictQueryParametersMixin, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
