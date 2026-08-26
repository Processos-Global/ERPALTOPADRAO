from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from usuarios.models import Notificacao


@login_required
def lista_notificacoes(request):
    status = (request.GET.get("status") or "todas").strip().lower()
    busca = (request.GET.get("q") or "").strip()

    notificacoes = Notificacao.objects.filter(usuario=request.user)

    if status == "nao_lidas":
        notificacoes = notificacoes.filter(lida=False)
    elif status == "lidas":
        notificacoes = notificacoes.filter(lida=True)
    elif status != "todas":
        status = "todas"

    if busca:
        notificacoes = notificacoes.filter(
            Q(titulo__icontains=busca)
            | Q(mensagem__icontains=busca)
            | Q(evento__icontains=busca)
        )

    context = {
        "notificacoes": notificacoes[:200],
        "filtro_status": status,
        "busca": busca,
        "total_nao_lidas": Notificacao.objects.filter(
            usuario=request.user,
            lida=False,
        ).count(),
    }
    return render(request, "usuarios/notificacoes.html", context)


@login_required
def abrir_notificacao(request, notificacao_id):
    notificacao = get_object_or_404(
        Notificacao,
        pk=notificacao_id,
        usuario=request.user,
    )
    notificacao.marcar_como_lida()

    destino = (notificacao.url or "").strip()

    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destino)

    if destino.startswith("/"):
        return redirect(destino)

    return redirect("usuarios:notificacoes")


@login_required
def marcar_todas_notificacoes_lidas(request):
    if request.method != "POST":
        raise Http404

    agora = timezone.now()
    Notificacao.objects.filter(
        usuario=request.user,
        lida=False,
    ).update(lida=True, lida_em=agora)

    proximo = (request.POST.get("next") or "").strip()
    if proximo and proximo.startswith("/"):
        return redirect(proximo)

    return redirect(reverse("usuarios:notificacoes"))
