from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.models import AcaoCompra

from compras.forms.contrato import ContratoAssinadoForm, ContratoCompraForm, DecisaoContratoForm
from compras.models import ContratoCompra
from compras.services.contratos import (
    atualizar_contrato,
    confirmar_assinatura,
    criar_contrato,
    decidir_contrato,
    enviar_para_aprovacao,
    gerar_previa,
)
from compras.services.permissoes import compras_acao_required, possui_acao_compras


def _contrato(pk):
    return get_object_or_404(
        ContratoCompra.objects.select_related("obra", "fornecedor", "processo", "criado_por", "aprovado_por"),
        pk=pk,
    )


def _pode_editar_usuario(request, contrato):
    return (
        request.user.is_superuser
        or contrato.criado_por_id == request.user.id
        or possui_acao_compras(request.user, AcaoCompra.ADMINISTRAR)
    )


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contratos_dashboard(request):
    qs = ContratoCompra.objects.select_related("obra", "fornecedor", "criado_por")
    status = (request.GET.get("status") or "").strip()
    busca = (request.GET.get("q") or "").strip()
    if status:
        qs = qs.filter(status=status)
    if busca:
        qs = qs.filter(
            Q(numero__icontains=busca)
            | Q(contratado_razao_social__icontains=busca)
            | Q(obra__nome__icontains=busca)
        )
    totais = dict(ContratoCompra.objects.values_list("status").annotate(total=Count("id")))
    return render(request, "compras/contratos/dashboard.html", {
        "contratos": qs[:300],
        "status_choices": ContratoCompra.Status.choices,
        "status_filtro": status,
        "busca": busca,
        "totais": totais,
        "pode_criar": possui_acao_compras(request.user, AcaoCompra.NEGOCIAR)
            or possui_acao_compras(request.user, AcaoCompra.GERENCIAR_PEDIDOS)
            or possui_acao_compras(request.user, AcaoCompra.ADMINISTRAR),
        "pode_aprovar": possui_acao_compras(request.user, AcaoCompra.APROVAR),
    })


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_novo(request):
    if not any(possui_acao_compras(request.user, acao) for acao in (AcaoCompra.NEGOCIAR, AcaoCompra.GERENCIAR_PEDIDOS, AcaoCompra.ADMINISTRAR)):
        raise PermissionDenied("Você não possui permissão para criar contratos.")
    form = ContratoCompraForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            contrato = criar_contrato(form=form, usuario=request.user)
            messages.success(request, f"Contrato {contrato.numero} criado.")
            return redirect("compras:contrato_detalhe", pk=contrato.pk)
        except Exception as exc:
            messages.error(request, f"Não foi possível criar o contrato: {exc}")
    return render(request, "compras/contratos/form.html", {"form": form, "titulo": "Novo contrato"})


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_detalhe(request, pk):
    contrato = _contrato(pk)
    pode_editar = contrato.pode_editar and _pode_editar_usuario(request, contrato)
    pode_confirmar_assinatura = (
        contrato.status == ContratoCompra.Status.AGUARDANDO_ASSINATURA
        and _pode_editar_usuario(request, contrato)
    )
    pode_aprovar = possui_acao_compras(request.user, AcaoCompra.APROVAR)
    return render(request, "compras/contratos/detalhe.html", {
        "contrato": contrato,
        "pode_editar": pode_editar,
        "pode_confirmar_assinatura": pode_confirmar_assinatura,
        "pode_aprovar": pode_aprovar,
        "decisao_form": DecisaoContratoForm(),
        "assinado_form": ContratoAssinadoForm(instance=contrato),
    })


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_editar(request, pk):
    contrato = _contrato(pk)
    if not _pode_editar_usuario(request, contrato):
        raise PermissionDenied("Somente o criador ou administrador pode editar este contrato.")
    if not contrato.pode_editar:
        messages.error(request, "Este contrato não pode mais ser editado.")
        return redirect("compras:contrato_detalhe", pk=pk)

    form = ContratoCompraForm(request.POST or None, instance=contrato)
    if request.method == "POST" and form.is_valid():
        try:
            atualizar_contrato(form=form, usuario=request.user)
            messages.success(request, "Contrato atualizado.")
            return redirect("compras:contrato_detalhe", pk=pk)
        except Exception as exc:
            messages.error(request, str(exc))
    return render(request, "compras/contratos/form.html", {"form": form, "titulo": f"Editar {contrato.numero}", "contrato": contrato})


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_gerar_previa(request, pk):
    contrato = _contrato(pk)
    if request.method != "POST":
        return redirect("compras:contrato_detalhe", pk=pk)
    if not _pode_editar_usuario(request, contrato):
        raise PermissionDenied("Você não pode gerar a prévia deste contrato.")
    try:
        gerar_previa(contrato=contrato, usuario=request.user)
        messages.success(request, "Prévia atualizada no Google Drive.")
    except Exception as exc:
        messages.error(request, f"Erro ao gerar prévia: {exc}")
    return redirect("compras:contrato_detalhe", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_enviar_aprovacao(request, pk):
    contrato = _contrato(pk)
    if request.method != "POST":
        return redirect("compras:contrato_detalhe", pk=pk)
    if not _pode_editar_usuario(request, contrato):
        raise PermissionDenied("Você não pode enviar este contrato para aprovação.")
    try:
        enviar_para_aprovacao(contrato=contrato, usuario=request.user)
        messages.success(request, "Contrato enviado para aprovação do gestor.")
    except Exception as exc:
        messages.error(request, f"Não foi possível enviar para aprovação: {exc}")
    return redirect("compras:contrato_detalhe", pk=pk)


@compras_acao_required(AcaoCompra.APROVAR)
def contrato_decidir(request, pk):
    contrato = _contrato(pk)
    if request.method != "POST":
        return redirect("compras:contrato_detalhe", pk=pk)
    form = DecisaoContratoForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("compras:contrato_detalhe", pk=pk)
    try:
        decidir_contrato(
            contrato=contrato,
            usuario=request.user,
            decisao=form.cleaned_data["decisao"],
            observacao=form.cleaned_data["observacao"],
        )
        messages.success(request, "Decisão registrada.")
    except Exception as exc:
        messages.error(request, f"Não foi possível registrar a decisão: {exc}")
    return redirect("compras:contrato_detalhe", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_confirmar_assinatura(request, pk):
    contrato = _contrato(pk)
    if request.method != "POST":
        return redirect("compras:contrato_detalhe", pk=pk)
    if not _pode_editar_usuario(request, contrato):
        raise PermissionDenied("Você não pode concluir a assinatura deste contrato.")
    form = ContratoAssinadoForm(request.POST, request.FILES, instance=contrato)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("compras:contrato_detalhe", pk=pk)
    try:
        confirmar_assinatura(
            contrato=contrato,
            arquivo=form.cleaned_data["arquivo_assinado"],
            usuario=request.user,
        )
        messages.success(request, "Contrato marcado como assinado e salvo no Google Drive.")
    except Exception as exc:
        messages.error(request, f"Não foi possível concluir a assinatura: {exc}")
    return redirect("compras:contrato_detalhe", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_fornecedor_dados(request, pk):
    from django.apps import apps
    Fornecedor = apps.get_model("cadastros", "Fornecedor")
    fornecedor = get_object_or_404(Fornecedor, pk=pk)

    def first(*names):
        for name in names:
            value = getattr(fornecedor, name, None)
            if value not in (None, ""):
                return str(value)
        return ""

    endereco = first("endereco", "endereco_completo")
    if not endereco:
        partes = [first("logradouro"), first("numero"), first("complemento"), first("bairro"), first("cidade"), first("uf")]
        endereco = ", ".join(x for x in partes if x)

    return JsonResponse({
        "razao_social": first("razao_social", "nome_empresarial", "nome"),
        "cnpj": first("cnpj", "cpf_cnpj", "documento"),
        "endereco": endereco,
        "email": first("email", "email_principal"),
        "favorecido_nome": first("titular", "nome_titular", "razao_social", "nome"),
        "favorecido_documento": first("cnpj", "cpf_cnpj", "documento"),
        "banco": first("banco"),
        "agencia": first("agencia"),
        "conta": first("conta_corrente", "conta"),
        "operacao": first("operacao"),
        "pix": first("pix", "chave_pix"),
    })


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_baixar_docx(request, pk):
    contrato = _contrato(pk)
    if not contrato.arquivo_docx:
        messages.error(request, "O DOCX ainda não foi gerado.")
        return redirect("compras:contrato_detalhe", pk=pk)
    arquivo = contrato.arquivo_docx
    arquivo.open("rb")
    return FileResponse(arquivo, as_attachment=True, filename=arquivo.name.rsplit("/", 1)[-1])


@compras_acao_required(AcaoCompra.VISUALIZAR)
def contrato_baixar_assinado(request, pk):
    contrato = _contrato(pk)
    if not contrato.arquivo_assinado:
        messages.error(request, "Contrato assinado ainda não anexado.")
        return redirect("compras:contrato_detalhe", pk=pk)
    arquivo = contrato.arquivo_assinado
    arquivo.open("rb")
    return FileResponse(arquivo, as_attachment=True, filename=arquivo.name.rsplit("/", 1)[-1])
