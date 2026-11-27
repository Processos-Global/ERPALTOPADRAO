from django.contrib.staticfiles import finders
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe


@require_safe
def service_worker(request):
    """Public, version-independent URL; no session or user information."""
    filename = finders.find("pwa/service-worker.js")
    if not filename:
        raise Http404("Service Worker indisponivel")
    response = FileResponse(open(filename, "rb"), content_type="text/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Service-Worker-Allowed"] = "/"
    response["X-Content-Type-Options"] = "nosniff"
    return response
