import mimetypes
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET
from core.storage import SaariPublicStorage


@login_required
@require_GET
def arquivo_publico(request, caminho):
    # Escopo: mídias anteriormente publicadas em /media/. Documentos privados
    # continuam acessíveis EXCLUSIVAMENTE pelas views autorizadas dos módulos.
    storage = SaariPublicStorage()
    if caminho.startswith('/') or '..' in caminho.split('/') or '\\' in caminho:
        raise Http404
    try:
        arquivo = storage.open(caminho, 'rb')
    except FileNotFoundError:
        raise Http404
    mime = mimetypes.guess_type(caminho)[0] or 'application/octet-stream'
    response = FileResponse(arquivo, content_type=mime)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=300'
    return response
