from django.views.generic import TemplateView


class KarizHomeView(TemplateView):
    template_name = "common/home.html"
