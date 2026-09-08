from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cadastros.forms import FornecedorForm, MaoObraForm, MaterialForm, UnidadeMedidaForm
from cadastros.models import Fornecedor, MaoObra, Material, UnidadeMedida
from usuarios.services import pode_acao_cadastros


def cadastros_permissao_required(acao):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not pode_acao_cadastros(request.user, acao):
                raise PermissionDenied("Você não possui permissão para executar esta ação em Cadastros.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def _permissoes_contexto(usuario):
    return {
        "cad_pode_criar": pode_acao_cadastros(usuario, "criar"),
        "cad_pode_editar": pode_acao_cadastros(usuario, "editar"),
        "cad_pode_excluir": pode_acao_cadastros(usuario, "excluir"),
        "cad_pode_administrar": pode_acao_cadastros(usuario, "administrar"),
    }


@cadastros_permissao_required("visualizar")
def index(request):
    contexto = {
        "total_materiais": Material.objects.filter(ativo=True).count(),
        "total_fornecedores": Fornecedor.objects.filter(ativo=True).count(),
        "total_mao_obra": MaoObra.objects.filter(ativo=True).count(),
        "total_unidades": UnidadeMedida.objects.filter(ativo=True).count(),
        **_permissoes_contexto(request.user),
    }
    return render(request, "cadastros/index.html", contexto)


@cadastros_permissao_required("visualizar")
def materiais_lista(request):
    qs = Material.objects.select_related("unidade")
    q = (request.GET.get("q") or "").strip()
    unidade_id = (request.GET.get("unidade") or "").strip()
    status = (request.GET.get("status") or "ativos").strip()

    if q:
        qs = qs.filter(
            Q(codigo__icontains=q)
            | Q(nome__icontains=q)
            | Q(especificacao__icontains=q)
        )
    if unidade_id.isdigit():
        qs = qs.filter(unidade_id=int(unidade_id))
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)

    contexto = {
        "materiais": qs[:1000],
        "q": q,
        "unidade_id": unidade_id,
        "status": status,
        "unidades": UnidadeMedida.objects.filter(ativo=True).order_by("sigla"),
        **_permissoes_contexto(request.user),
    }
    return render(request, "cadastros/materiais/lista.html", contexto)


@cadastros_permissao_required("criar")
def material_novo(request):
    form = MaterialForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        material = form.save()
        messages.success(request, f"Material {material.codigo} cadastrado com sucesso.")
        return redirect("cadastros:materiais_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": "Novo material",
        "subtitulo": "Adicione um item ao catálogo oficial de materiais.",
        "voltar": "cadastros:materiais_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def material_editar(request, pk):
    material = get_object_or_404(Material, pk=pk)
    form = MaterialForm(request.POST or None, instance=material)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Material atualizado com sucesso.")
        return redirect("cadastros:materiais_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": f"Editar {material.codigo}",
        "subtitulo": "Atualize os dados mestres deste material.",
        "voltar": "cadastros:materiais_lista",
        "objeto": material,
        "excluir_url": "cadastros:material_excluir",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("excluir")
@require_POST
def material_excluir(request, pk):
    material = get_object_or_404(Material, pk=pk)
    codigo = material.codigo
    try:
        material.delete()
        messages.success(request, f"Material {codigo} excluído com sucesso.")
    except ProtectedError:
        messages.error(request, "Este material possui vínculos protegidos e não pode ser excluído. Inative-o para preservar o histórico.")
    return redirect("cadastros:materiais_lista")


@cadastros_permissao_required("visualizar")
def fornecedores_lista(request):
    qs = Fornecedor.objects.all()
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "ativos").strip()
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q)
            | Q(nome__icontains=q)
            | Q(nome_fantasia__icontains=q)
            | Q(documento__icontains=q)
            | Q(email__icontains=q)
        )
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)
    return render(request, "cadastros/fornecedores/lista.html", {
        "fornecedores": qs[:1000], "q": q, "status": status,
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def fornecedor_novo(request):
    form = FornecedorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fornecedor = form.save()
        messages.success(request, f"Fornecedor {fornecedor.codigo} cadastrado com sucesso.")
        return redirect("cadastros:fornecedores_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": "Novo fornecedor",
        "subtitulo": "Cadastre um fornecedor para uso centralizado no ERP.",
        "voltar": "cadastros:fornecedores_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def fornecedor_editar(request, pk):
    fornecedor = get_object_or_404(Fornecedor, pk=pk)
    form = FornecedorForm(request.POST or None, instance=fornecedor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fornecedor atualizado com sucesso.")
        return redirect("cadastros:fornecedores_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": f"Editar {fornecedor.codigo}",
        "subtitulo": "Atualize os dados mestres deste fornecedor.",
        "voltar": "cadastros:fornecedores_lista",
        "objeto": fornecedor,
        "excluir_url": "cadastros:fornecedor_excluir",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("excluir")
@require_POST
def fornecedor_excluir(request, pk):
    fornecedor = get_object_or_404(Fornecedor, pk=pk)
    codigo = fornecedor.codigo
    try:
        fornecedor.delete()
        messages.success(request, f"Fornecedor {codigo} excluído com sucesso.")
    except ProtectedError:
        messages.error(request, "Este fornecedor possui vínculos protegidos e não pode ser excluído. Inative-o para preservar o histórico.")
    return redirect("cadastros:fornecedores_lista")


@cadastros_permissao_required("visualizar")
def mao_obra_lista(request):
    qs = MaoObra.objects.select_related("unidade")
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "ativos").strip()
    if q:
        qs = qs.filter(Q(codigo__icontains=q) | Q(descricao__icontains=q) | Q(categoria__icontains=q))
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)
    return render(request, "cadastros/mao_obra/lista.html", {
        "itens": qs[:1000], "q": q, "status": status,
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def mao_obra_nova(request):
    form = MaoObraForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"Mão de obra {item.codigo} cadastrada com sucesso.")
        return redirect("cadastros:mao_obra_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": "Nova mão de obra",
        "subtitulo": "Adicione um serviço ou recurso de mão de obra à base central.",
        "voltar": "cadastros:mao_obra_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def mao_obra_editar(request, pk):
    item = get_object_or_404(MaoObra, pk=pk)
    form = MaoObraForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mão de obra atualizada com sucesso.")
        return redirect("cadastros:mao_obra_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": f"Editar {item.codigo}",
        "subtitulo": "Atualize os dados mestres deste item de mão de obra.",
        "voltar": "cadastros:mao_obra_lista",
        "objeto": item,
        "excluir_url": "cadastros:mao_obra_excluir",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("excluir")
@require_POST
def mao_obra_excluir(request, pk):
    item = get_object_or_404(MaoObra, pk=pk)
    codigo = item.codigo
    try:
        item.delete()
        messages.success(request, f"Mão de obra {codigo} excluída com sucesso.")
    except ProtectedError:
        messages.error(request, "Este item possui vínculos protegidos e não pode ser excluído. Inative-o para preservar o histórico.")
    return redirect("cadastros:mao_obra_lista")


@cadastros_permissao_required("visualizar")
def unidades_lista(request):
    qs = UnidadeMedida.objects.all()
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "ativos").strip()
    if q:
        qs = qs.filter(Q(sigla__icontains=q) | Q(descricao__icontains=q))
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)
    return render(request, "cadastros/unidades/lista.html", {
        "unidades": qs.order_by("sigla")[:1000],
        "q": q,
        "status": status,
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def unidade_nova(request):
    form = UnidadeMedidaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        unidade = form.save()
        messages.success(request, f"Unidade {unidade.sigla} cadastrada com sucesso.")
        return redirect("cadastros:unidades_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": "Nova unidade de medida",
        "subtitulo": "Cadastre uma unidade para uso em materiais, mão de obra e processos do ERP.",
        "voltar": "cadastros:unidades_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def unidade_editar(request, pk):
    unidade = get_object_or_404(UnidadeMedida, pk=pk)
    form = UnidadeMedidaForm(request.POST or None, instance=unidade)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Unidade de medida atualizada com sucesso.")
        return redirect("cadastros:unidades_lista")
    return render(request, "cadastros/form.html", {
        "form": form,
        "titulo": f"Editar {unidade.sigla}",
        "subtitulo": "Atualize a sigla, descrição ou situação da unidade de medida.",
        "voltar": "cadastros:unidades_lista",
        "objeto": unidade,
        "excluir_url": "cadastros:unidade_excluir",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("excluir")
@require_POST
def unidade_excluir(request, pk):
    unidade = get_object_or_404(UnidadeMedida, pk=pk)
    sigla = unidade.sigla
    try:
        unidade.delete()
        messages.success(request, f"Unidade {sigla} excluída com sucesso.")
    except ProtectedError:
        messages.error(request, "Esta unidade já está sendo utilizada e não pode ser excluída. Inative-a para preservar o histórico.")
    return redirect("cadastros:unidades_lista")
