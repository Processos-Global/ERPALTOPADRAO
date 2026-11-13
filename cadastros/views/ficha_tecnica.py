from django.contrib import messages
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cadastros.forms import (
    CaracteristicaAmbienteForm,
    CategoriaGrandeFornecedorForm,
    OpcaoEspecificacaoGrandeFornecedorForm,
    TipoAmbienteForm,
    TipoItemGrandeFornecedorForm,
    TipoPavimentoForm,
)
from cadastros.models import (
    CaracteristicaAmbiente,
    CategoriaGrandeFornecedor,
    OpcaoEspecificacaoGrandeFornecedor,
    TipoAmbiente,
    TipoItemGrandeFornecedor,
    TipoPavimento,
)
from .cadastros import cadastros_permissao_required, _permissoes_contexto


CONFIG = {
    "pavimentos": (TipoPavimento, TipoPavimentoForm, "Tipos de pavimento"),
    "caracteristicas": (CaracteristicaAmbiente, CaracteristicaAmbienteForm, "Características de ambiente"),
    "ambientes": (TipoAmbiente, TipoAmbienteForm, "Tipos de ambiente"),
    "categorias-gf": (CategoriaGrandeFornecedor, CategoriaGrandeFornecedorForm, "Categorias de Grandes Fornecedores"),
    "itens-gf": (TipoItemGrandeFornecedor, TipoItemGrandeFornecedorForm, "Tipos de itens de Grandes Fornecedores"),
    "especificacoes-gf": (OpcaoEspecificacaoGrandeFornecedor, OpcaoEspecificacaoGrandeFornecedorForm, "Opções de especificação"),
}


def _cfg(tipo):
    return CONFIG.get(tipo)


@cadastros_permissao_required("visualizar")
def ficha_tecnica_cadastros(request):
    return render(request, "cadastros/ficha_tecnica/index.html", {
        "totais": {
            "pavimentos": TipoPavimento.objects.filter(ativo=True).count(),
            "caracteristicas": CaracteristicaAmbiente.objects.filter(ativo=True).count(),
            "ambientes": TipoAmbiente.objects.filter(ativo=True).count(),
            "categorias_gf": CategoriaGrandeFornecedor.objects.filter(ativo=True).count(),
            "itens_gf": TipoItemGrandeFornecedor.objects.filter(ativo=True).count(),
            "especificacoes_gf": OpcaoEspecificacaoGrandeFornecedor.objects.filter(ativo=True).count(),
        },
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("visualizar")
def ficha_tecnica_lista(request, tipo):
    cfg = _cfg(tipo)
    if not cfg:
        return redirect("cadastros:ficha_tecnica_cadastros")
    model, _form, titulo = cfg
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "ativos").strip()
    qs = model.objects.all()
    if q:
        campos = [f.name for f in model._meta.fields]
        filtro = Q()
        for campo in ("nome", "codigo"):
            if campo in campos:
                filtro |= Q(**{f"{campo}__icontains": q})
        if filtro:
            qs = qs.filter(filtro)
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)
    return render(request, "cadastros/ficha_tecnica/lista.html", {
        "tipo": tipo,
        "titulo": titulo,
        "itens": qs[:1500],
        "q": q,
        "status": status,
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def ficha_tecnica_novo(request, tipo):
    cfg = _cfg(tipo)
    if not cfg:
        return redirect("cadastros:ficha_tecnica_cadastros")
    _model, form_class, titulo = cfg
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cadastro salvo com sucesso.")
        return redirect("cadastros:ficha_tecnica_lista", tipo=tipo)
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": f"Novo · {titulo}",
        "subtitulo": "Cadastro mestre utilizado pela Ficha Técnica das Obras.",
        "voltar": "cadastros:ficha_tecnica_cadastros",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def ficha_tecnica_editar(request, tipo, pk):
    cfg = _cfg(tipo)
    if not cfg:
        return redirect("cadastros:ficha_tecnica_cadastros")
    model, form_class, titulo = cfg
    objeto = get_object_or_404(model, pk=pk)
    form = form_class(request.POST or None, instance=objeto)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cadastro atualizado com sucesso.")
        return redirect("cadastros:ficha_tecnica_lista", tipo=tipo)
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": f"Editar · {titulo}",
        "subtitulo": str(objeto),
        "voltar": "cadastros:ficha_tecnica_cadastros",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("excluir")
@require_POST
def ficha_tecnica_excluir(request, tipo, pk):
    cfg = _cfg(tipo)
    if not cfg:
        return redirect("cadastros:ficha_tecnica_cadastros")
    model, _form, _titulo = cfg
    objeto = get_object_or_404(model, pk=pk)
    try:
        objeto.delete()
        messages.success(request, "Cadastro excluído com sucesso.")
    except ProtectedError:
        messages.error(request, "Este cadastro já possui vínculos. Inative-o para preservar o histórico.")
    return redirect("cadastros:ficha_tecnica_lista", tipo=tipo)
