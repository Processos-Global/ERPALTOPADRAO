from datetime import date

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.validators import validar_documento_upload
from financeiro.models import Pagamento, TituloPagar
from financeiro.services.agenda import titulos_disponiveis_pagamento
from financeiro.services.pagamentos import estornar_pagamento, programar_pagamento, registrar_pagamento
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro


ABAS_PAGAMENTOS = (
    ("disponiveis", "Disponíveis"), ("programados", "Programados"), ("pacotes", "Pacotes"),
    ("efetivados", "Efetivados"), ("estornos", "Estornos"),
)


class ConfirmacaoPagamentoForm(forms.Form):
    pago = forms.BooleanField(required=False, label="Confirmar pagamento integral")
    data_pagamento = forms.DateField(required=False, label="Data efetiva", widget=forms.DateInput(attrs={"type": "date"}))
    forma = forms.ChoiceField(required=False, choices=Pagamento.Forma.choices, label="Forma")
    comprovante = forms.FileField(required=False, validators=[validar_documento_upload])


class ProgramacaoPagamentoForm(forms.Form):
    data_programada = forms.DateField(label="Data programada", widget=forms.DateInput(attrs={"type": "date"}))
    motivo = forms.CharField(required=False, max_length=400, label="Motivo")


def titulos_central_pagamentos(parametros, aba):
    programacao_valida = Q(programacao_pagamento__ativa=True, programacao_pagamento__ciclo_aprovacao=F("ciclo_aprovacao"))
    titulos = titulos_disponiveis_pagamento(TituloPagar.objects.all()).select_related(
        "obra", "fornecedor", "pagamento", "programacao_pagamento",
    )
    if aba == "programados":
        return titulos.filter(programacao_valida).order_by("programacao_pagamento__data_programada", "numero")
    if parametros.get("periodo") == "vencidas_e_hoje":
        return titulos.filter(vencimento__lte=timezone.localdate())
    return titulos.exclude(programacao_valida)


def recorte_pagamentos(parametros, aba):
    mes_filtro = (parametros.get("mes") or "").strip()
    qs = Pagamento.objects.select_related(
        "titulo", "titulo__fornecedor", "titulo__obra", "titulo__plano_financeiro", "registrado_por"
    ).order_by("-data_pagamento", "-id")
    if aba == "efetivados":
        qs = qs.filter(status=Pagamento.Status.EFETIVADO)
    elif aba == "estornos":
        qs = qs.filter(status=Pagamento.Status.ESTORNADO).order_by("-estornado_em", "-id")
    try:
        ano, mes = (int(parte) for parte in mes_filtro.split("-"))
        inicio = date(ano, mes, 1)
        fim = date(ano + (mes == 12), mes % 12 + 1, 1)
    except (ValueError, TypeError):
        mes_filtro = ""
    else:
        if aba == "estornos":
            qs = qs.filter(estornado_em__date__gte=inicio, estornado_em__date__lt=fim)
        else:
            qs = qs.filter(data_pagamento__gte=inicio, data_pagamento__lt=fim)
    return qs, mes_filtro


@financeiro_acao_required("VISUALIZAR")
def pagamentos_lista(request):
    aba = request.GET.get("aba")
    if aba == "pacotes":
        return redirect("financeiro:relatorios_pagamento")
    if aba not in dict(ABAS_PAGAMENTOS):
        aba = "historico" if request.GET.get("mes") else "disponiveis"
    pode_pagar = possui_acao_financeiro(request.user, "PAGAR")
    if aba in {"disponiveis", "programados"}:
        titulos = titulos_central_pagamentos(request.GET, aba)
        return render(request, "financeiro/pagamentos.html", {
            "aba": aba, "abas_pagamentos": ABAS_PAGAMENTOS, "por_titulo": True,
            "page_obj": Paginator(titulos, 30).get_page(request.GET.get("page")), "pode_pagar": pode_pagar,
        })

    qs, mes_filtro = recorte_pagamentos(request.GET, aba)
    total_pago = qs.filter(status=Pagamento.Status.EFETIVADO).aggregate(total=Sum("valor"))["total"] or 0
    page_obj = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "financeiro/pagamentos.html", {
        "page_obj": page_obj,
        "mes_filtro": mes_filtro,
        "total_pago": total_pago,
        "total_estornado": qs.aggregate(total=Sum("valor"))["total"] or 0 if aba == "estornos" else 0,
        "aba": aba, "abas_pagamentos": ABAS_PAGAMENTOS, "pode_pagar": pode_pagar,
    })


@financeiro_acao_required("PAGAR")
def pagamento_novo(request, titulo_id):
    titulo = get_object_or_404(
        TituloPagar.objects.select_related("fornecedor", "obra", "plano_financeiro"),
        pk=titulo_id,
    )

    pagamento_existente = Pagamento.objects.filter(titulo=titulo).first()
    if (pagamento_existente and pagamento_existente.status == Pagamento.Status.EFETIVADO) or titulo.status == TituloPagar.Status.PAGO:
        messages.warning(request, "Esta Conta a Pagar já possui pagamento registrado.")
        return redirect("financeiro:titulos")

    if titulo.status != TituloPagar.Status.APROVADO:
        messages.error(request, "A Conta a Pagar precisa estar aprovada antes de registrar o pagamento.")
        return redirect("financeiro:titulos")

    if request.method == "POST":
        form = ConfirmacaoPagamentoForm(request.POST, request.FILES)
        if form.is_valid():
            if not form.cleaned_data.get("pago"):
                messages.info(request, "A conta permanece aprovada e não foi marcada como paga.")
                return redirect("financeiro:titulos")
            try:
                pagamento = registrar_pagamento(
                    titulo=titulo,
                    data_pagamento=form.cleaned_data["data_pagamento"],
                    forma=form.cleaned_data["forma"],
                    comprovante=form.cleaned_data["comprovante"],
                    usuario=request.user,
                )
                messages.success(request, f"Pagamento de R$ {pagamento.valor:,.2f} marcado como pago.")
                return redirect("financeiro:pagamentos")
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
    else:
        form = ConfirmacaoPagamentoForm(initial={"data_pagamento": timezone.localdate(), "forma": Pagamento.Forma.OUTRO})

    return render(request, "financeiro/pagamento_form.html", {
        "form": form, "titulo": titulo, "form_programacao": ProgramacaoPagamentoForm(),
    })


@financeiro_acao_required("PAGAR")
@require_POST
def pagamento_programar(request, titulo_id):
    titulo = get_object_or_404(TituloPagar, pk=titulo_id)
    form = ProgramacaoPagamentoForm(request.POST)
    if form.is_valid():
        try:
            programar_pagamento(titulo, usuario=request.user, **form.cleaned_data)
        except ValidationError as erro:
            messages.error(request, "; ".join(erro.messages))
        else:
            messages.success(request, "Programação registrada.")
            return redirect(f"{reverse('financeiro:pagamentos')}?aba=programados")
    else:
        messages.error(request, "Informe uma data e um motivo válido para a programação.")
    return redirect("financeiro:pagamento_novo", titulo_id=titulo.pk)


@financeiro_acao_required("PAGAR")
@require_POST
def pagamento_confirmar_direto(request, titulo_id):
    """Confirma integralmente uma conta aprovada direto da listagem de Contas a Pagar."""
    titulo = get_object_or_404(TituloPagar, pk=titulo_id)

    try:
        pagamento = registrar_pagamento(
            titulo=titulo,
            data_pagamento=timezone.localdate(),
            forma=Pagamento.Forma.OUTRO,
            usuario=request.user,
        )
    except ValidationError as exc:
        return JsonResponse(
            {"ok": False, "message": "; ".join(exc.messages)},
            status=400,
        )

    return JsonResponse({
        "ok": True,
        "message": f"Pagamento de R$ {pagamento.valor:,.2f} confirmado com sucesso.",
        "status": TituloPagar.Status.PAGO,
        "status_display": TituloPagar.Status.PAGO.label,
        "data_pagamento": pagamento.data_pagamento.strftime("%d/%m/%Y"),
    })


@financeiro_acao_required("PAGAR")
@require_POST
def pagamento_estornar(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    estornar_pagamento(
        pagamento,
        usuario=request.user,
        motivo=(request.POST.get("motivo") or "").strip(),
    )
    messages.success(request, "Pagamento estornado. A Conta a Pagar voltou para o status Aprovado.")
    return redirect("financeiro:pagamentos")
