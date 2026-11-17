"""Mapa de concretagem (por obra e local de uso) e formatos de desenho."""
import json
from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.db import transaction
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from obras.models import (
    FormatoDesenho, LocalUsoObra, MapaLocal, Obra,
)
from obras.models.concretagem.mapa import MAX_DIMENSAO
from obras.services.concretagem import mapa as svc
from obras.services.concretagem.fluxo import FluxoError
from obras.services.concretagem.permissoes import (
    contexto_permissoes, gerente_required, pode_preencher, preencher_required, ver_required,
)

def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def _voltar_seguro(request):
    """URL interna para retornar depois de criar/propor um formato (vinda do mapa)."""
    voltar = request.GET.get("voltar") or ""
    if voltar and url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return voltar
    return ""


LIMITE_FORMATOS = 60


def _buscar_formatos(q=""):
    """(lista até o limite, total) dos formatos ativos cujo nome contém `q`."""
    qs = FormatoDesenho.objects.filter(ativo=True).select_related("obra_origem").order_by("nome")
    q = (q or "").strip()
    if q:
        qs = qs.filter(nome__icontains=q)
    return list(qs[:LIMITE_FORMATOS]), qs.count()


def _params_formato(obra, local):
    """Criar/editar a partir do mapa: salva, aplica neste local e volta para cá."""
    voltar = reverse("obras:concretagem_mapa", args=[obra.pk]) + f"?local={local.pk}"
    return urlencode({"obra": obra.pk, "local": local.pk, "voltar": voltar})


def _formato_json(f):
    return {"id": f.pk, "nome": f.nome, "linhas": f.linhas, "colunas": f.colunas, "fora": f.celulas_fora}


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

@ver_required
def mapa(request, obra_id):
    """Mapa da obra. O local só abre quando escolhido (?local=); sem ele a página pede a escolha."""
    obra = get_object_or_404(Obra, pk=obra_id)
    locais = list(svc.resumo_locais(obra))
    local = None
    local_id = request.GET.get("local")
    if local_id and local_id.isdigit():
        local = next((l for l in locais if l.pk == int(local_id)), None)
    mapa_obj = svc.mapa_do_local(local) if local else None
    formatos, formatos_total = _buscar_formatos()
    contexto = {
        "obra": obra, "locais": locais, "local": local, "mapa": mapa_obj,
        "formatos": formatos, "formatos_total": formatos_total, "max_dimensao": MAX_DIMENSAO,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        **contexto_permissoes(request.user),
    }
    if local:
        itens = svc.itens_paleta(local)
        contexto["params_formato"] = _params_formato(obra, local)
        contexto["dados_mapa"] = {
            "mapa_id": mapa_obj.pk if mapa_obj else None,
            "linhas": mapa_obj.linhas if mapa_obj else 0,
            "colunas": mapa_obj.colunas if mapa_obj else 0,
            "fora": mapa_obj.celulas_fora if mapa_obj else [],
            "celulas": svc.estado_mapa(mapa_obj) if mapa_obj else {},
            "itens": itens,
            "qtd_usos": sum(1 for i in itens if i["tipo"] == "Uso"),
            "qtd_sobras": sum(1 for i in itens if i["tipo"] != "Uso"),
            "url_pintar": reverse("obras:concretagem_mapa_pintar", args=[obra.pk, local.pk]),
            "pode_pintar": pode_preencher(request.user),
        }
    return render(request, "obras/concretagem/mapa.html", contexto)


@require_POST
@preencher_required
def mapa_definir(request, obra_id, local_id):
    """A grade sempre vem de um formato aprovado (tamanho e contorno prontos)."""
    local = get_object_or_404(LocalUsoObra, pk=local_id, obra_id=obra_id)
    formato_id = request.POST.get("formato") or ""
    if not formato_id.isdigit():
        messages.error(request, "Escolha um formato pronto ou crie um novo.")
        return redirect(reverse("obras:concretagem_mapa", args=[obra_id]) + f"?local={local.pk}")
    formato = get_object_or_404(FormatoDesenho, pk=formato_id, ativo=True)
    try:
        svc.definir_mapa(local, request.user, formato=formato)
    except FluxoError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Formato “{formato.nome}” aplicado.")
    return redirect(reverse("obras:concretagem_mapa", args=[obra_id]) + f"?local={local.pk}")


@require_POST
@preencher_required
def mapa_pintar(request, obra_id, local_id):
    local = get_object_or_404(LocalUsoObra, pk=local_id, obra_id=obra_id)
    mapa_obj = get_object_or_404(MapaLocal, local=local)
    dados = _json_body(request)
    try:
        qtd = svc.pintar(mapa_obj, dados.get("celulas"), dados.get("item") or "", request.user)
    except FluxoError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
    return JsonResponse({"ok": True, "alteradas": qtd})


# ---------------------------------------------------------------------------
# Formatos de desenho
# ---------------------------------------------------------------------------

@ver_required
def formatos(request):
    formatos, total = _buscar_formatos()
    return render(request, "obras/concretagem/formatos.html", {
        "formatos": formatos, "formatos_total": total,
        **contexto_permissoes(request.user),
    })


@ver_required
def formatos_buscar(request):
    """Busca por nome (AJAX). modo=mapa devolve os cartões do seletor do mapa; senão, os da página Formatos."""
    formatos, total = _buscar_formatos(request.GET.get("q"))
    contexto = {"formatos": formatos, **contexto_permissoes(request.user)}
    if request.GET.get("modo") == "mapa":
        local_id = request.GET.get("local") or ""
        local = get_object_or_404(LocalUsoObra.objects.select_related("obra"), pk=local_id) if local_id.isdigit() else None
        if local is None:
            return JsonResponse({"ok": False, "erro": "Local inválido."}, status=400)
        mapa_obj = svc.mapa_do_local(local)
        contexto.update(atual_id=mapa_obj.formato_id if mapa_obj else None, params_formato=_params_formato(local.obra, local))
        html = render_to_string("obras/concretagem/_formatos_itens_mapa.html", contexto, request=request)
    else:
        html = render_to_string("obras/concretagem/_formatos_itens_lista.html", contexto, request=request)
    return JsonResponse({"ok": True, "html": html, "total": total, "mostrando": len(formatos)})


@preencher_required
def formato_editor(request, pk=None):
    """Cria ou edita um formato direto, sem aprovação. Vindo do mapa (?local=), já aplica no local.

    Ao editar um existente, `como_novo` cria uma cópia (o original e seus mapas não mudam);
    sem ele, grava sobre o original (a tela avisa antes, pois afeta os mapas que o usam).
    """
    formato = get_object_or_404(FormatoDesenho, pk=pk, ativo=True) if pk else None
    voltar = _voltar_seguro(request)
    local_id = request.GET.get("local") or ""
    local = get_object_or_404(LocalUsoObra, pk=local_id) if local_id.isdigit() else None
    if request.method == "POST":
        dados = _json_body(request)
        obra = Obra.objects.filter(pk=dados["obra"]).first() if dados.get("obra") else None
        alvo = None if dados.get("como_novo") else formato
        try:
            with transaction.atomic():
                obj = svc.salvar_formato(
                    request.user, dados.get("nome"), dados.get("linhas"), dados.get("colunas"),
                    dados.get("fora") or [], obra=obra, formato=alvo,
                )
                if local is not None:
                    svc.definir_mapa(local, request.user, formato=obj)
        except FluxoError as exc:
            return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
        acao = "criado" if alvo is None and formato is not None else "salvo"
        if local is not None:
            messages.success(request, f"Formato “{obj.nome}” {acao} e aplicado em {local.descricao_completa}.")
        else:
            messages.success(request, f"Formato “{obj.nome}” {acao}.")
        return JsonResponse({"ok": True, "redirecionar": voltar or reverse("obras:concretagem_formatos")})
    obra_get = request.GET.get("obra") or ""
    return render(request, "obras/concretagem/formato_editor.html", {
        "formato": formato,
        "local": local,
        "inicial": {
            "nome": formato.nome if formato else "",
            "linhas": formato.linhas if formato else 10,
            "colunas": formato.colunas if formato else 10,
            "fora": formato.celulas_fora if formato else [],
            "obra": formato.obra_origem_id if formato else (int(obra_get) if obra_get.isdigit() else None),
        },
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "max_dimensao": MAX_DIMENSAO,
        "travar_tamanho": bool(formato and formato.mapas.exists()),
        "mapas_qtd": formato.mapas.count() if formato else 0,
        "voltar": voltar,
        **contexto_permissoes(request.user),
    })


@require_POST
@gerente_required
def formato_desativar(request, pk):
    formato = get_object_or_404(FormatoDesenho, pk=pk)
    if formato.mapas.exists():
        messages.error(request, "Este formato está aplicado em mapas e não pode ser removido.")
    else:
        formato.ativo = False
        formato.save(update_fields=["ativo", "atualizado_em"])
        messages.success(request, f"Formato “{formato.nome}” removido da lista.")
    return redirect("obras:concretagem_formatos")


@ver_required
def mapa_inicio(request):
    """Entrada pelo painel/menu: pede a escolha da obra, sem abrir nenhuma automaticamente."""
    return render(request, "obras/concretagem/mapa.html", {
        "obra": None, "locais": [], "local": None, "mapa": None,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        **contexto_permissoes(request.user),
    })
