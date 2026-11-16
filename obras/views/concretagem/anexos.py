"""Fotos e documentos da concretagem (destino: Google Drive)."""
import mimetypes

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from obras.models import AnexoConcretagem, Concretagem
from obras.services.concretagem import drive, fluxo
from obras.services.concretagem.permissoes import preencher_required, ver_required

MAX_BYTES = 15 * 1024 * 1024
TIPOS_IMAGEM = {"image/jpeg", "image/png", "image/webp"}
TIPOS_DOC = TIPOS_IMAGEM | {"application/pdf"}


def validar_arquivo(arquivo, so_imagem=False):
    """Levanta ValueError com mensagem amigável se o arquivo não for aceito."""
    tipo = getattr(arquivo, "content_type", "") or mimetypes.guess_type(arquivo.name)[0] or ""
    permitidos = TIPOS_IMAGEM if so_imagem else TIPOS_DOC
    if tipo not in permitidos:
        raise ValueError(f"{arquivo.name}: envie {'uma foto (JPG, PNG ou WEBP)' if so_imagem else 'foto (JPG, PNG, WEBP) ou PDF'}.")
    if arquivo.size > MAX_BYTES:
        raise ValueError(f"{arquivo.name}: o arquivo passa de 15 MB.")
    cabeca = arquivo.read(8)
    arquivo.seek(0)
    if tipo == "application/pdf" and not cabeca.startswith(b"%PDF"):
        raise ValueError(f"{arquivo.name}: não é um PDF válido.")
    if tipo in TIPOS_IMAGEM:
        from PIL import Image

        try:
            Image.open(arquivo).verify()
        except Exception:
            raise ValueError(f"{arquivo.name}: não é uma imagem válida.")
        finally:
            arquivo.seek(0)


def _voltar(pk, aba="anexos"):
    return redirect(reverse("obras:concretagem_detalhe", args=[pk]) + f"#aba-{aba}")


@ver_required
def anexo_abrir(request, pk, anexo_pk):
    anexo = get_object_or_404(AnexoConcretagem, pk=anexo_pk, concretagem_id=pk, ativo=True)
    if anexo.drive_url:
        return redirect(anexo.drive_url)
    if not anexo.arquivo:
        raise Http404("Arquivo indisponível.")
    resposta = FileResponse(anexo.arquivo.open("rb"), content_type=anexo.tipo_conteudo or "application/octet-stream")
    resposta["Content-Disposition"] = f'inline; filename="{anexo.nome_original}"'
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta


@ver_required
def pasta_drive(request, pk, etapa):
    """Abre no Drive a subpasta da etapa (ex.: 03 Moldagem CPs) desta concretagem."""
    conc = get_object_or_404(Concretagem, pk=pk)
    voltar = reverse("obras:concretagem_detalhe", args=[pk])
    if not conc.drive_pasta_id:
        messages.info(request, "A pasta desta concretagem ainda não foi criada no Drive.")
        return redirect(voltar)
    subpasta = drive.SUBPASTA_POR_ETAPA.get(etapa)
    if subpasta and drive.drive_habilitado():
        try:
            from core.services.arquivos_drive import obter_pasta

            return redirect(f"https://drive.google.com/drive/folders/{obter_pasta(conc.drive_pasta_id, subpasta)}")
        except Exception:
            drive.logger.exception("Falha ao localizar a subpasta %s da concretagem %s", subpasta, conc.codigo)
    return redirect(conc.drive_pasta_url)


@require_POST
@preencher_required
def anexo_remover(request, pk, anexo_pk):
    """Tira o anexo do sistema. O arquivo já enviado continua no Drive."""
    anexo = get_object_or_404(AnexoConcretagem, pk=anexo_pk, concretagem_id=pk, ativo=True)
    anexo.ativo = False
    anexo.save(update_fields=["ativo"])
    if anexo.arquivo:
        nome = anexo.arquivo.name
        anexo.arquivo = ""
        anexo.save(update_fields=["arquivo"])
        anexo._meta.get_field("arquivo").storage.delete(nome)
    fluxo.registrar_historico(anexo.concretagem, request.user, fluxo.A.ANEXO, f"Anexo removido: {anexo.nome_original}.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from django.http import JsonResponse
        return JsonResponse({"ok": True})
    messages.success(request, "Anexo removido do sistema." + (" O arquivo continua no Drive." if anexo.drive_id else ""))
    return _voltar(pk, request.POST.get("aba") or "anexos")


@require_POST
@preencher_required
def reenviar_pendentes(request, pk):
    conc = get_object_or_404(Concretagem, pk=pk)
    if not drive.drive_habilitado():
        messages.error(request, "O envio ao Drive está desligado nas configurações.")
        return _voltar(pk)
    qtd = drive.agendar_pendentes(conc)
    messages.success(request, f"{qtd} arquivo(s) sendo enviado(s) ao Drive em segundo plano. Pode continuar usando o sistema.")
    return _voltar(pk)


@ver_required
def anexo_miniatura(request, pk, anexo_pk):
    """Miniatura JPEG (até 480 px) de um anexo de imagem, do temporário ou baixado do Drive.

    Não grava nada no servidor; o navegador guarda em cache por um dia.
    """
    import io

    from django.http import HttpResponse
    from PIL import Image, ImageOps

    anexo = get_object_or_404(AnexoConcretagem, pk=anexo_pk, concretagem_id=pk, ativo=True)
    if not anexo.eh_imagem:
        raise Http404
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(drive.ler_bytes(anexo))))
        im.thumbnail((480, 480))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=80)
    except Exception:
        raise Http404("Miniatura indisponível.")
    resposta = HttpResponse(buf.getvalue(), content_type="image/jpeg")
    resposta["Cache-Control"] = "private, max-age=86400"
    return resposta


def _pendente_json(conc, a):
    return {
        "id": a.pk,
        "nome": a.nome_original,
        "tipo": a.get_etapa_display(),
        "origem": a.rotulo_origem,
        "situacao": a.situacao_drive,
        "erro": a.ultimo_erro,
        "tentativas": a.tentativas,
        "enviado_em": a.criado_em.strftime("%d/%m %H:%M"),
        "abrir": reverse("obras:concretagem_anexo_abrir", args=[conc.pk, a.pk]),
    }


@ver_required
def anexos_status(request, pk):
    """Situação dos envios ao Drive, consultada pela tela enquanto houver pendentes."""
    from django.http import JsonResponse

    conc = get_object_or_404(Concretagem, pk=pk)
    lista = [_pendente_json(conc, a) for a in drive.pendentes(conc).order_by("criado_em")]
    return JsonResponse({"total": len(lista), "pendentes": lista})
