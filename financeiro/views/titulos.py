from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods

from cadastros.models import Fornecedor, Material
from financeiro.forms import TituloPagarForm
from financeiro.forms.titulos import SolicitacaoAvulsaForm
from financeiro.models import AnexoTituloPagar
from financeiro.models import AprovacaoTituloFinanceiro, PlanoFinanceiro, TituloPagar
from financeiro.services.aprovacoes import decidir_titulo, enviar_para_aprovacao
from financeiro.services.agenda import _inteiro_positivo
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.services.solicitacoes_avulsas import (
    SolicitacaoAvulsaDivergente, SolicitacaoAvulsaInvalida, registrar_solicitacao_avulsa,
)
from financeiro.services.titulos import atualizar_titulo, cancelar_titulo
from obras.models import Obra



def _salvar_anexos(titulos, arquivos, usuario):
    arquivos = arquivos or []
    if not arquivos:
        return 0

    # Preserva o conteúdo para permitir que os mesmos comprovantes acompanhem
    # todas as parcelas criadas no mesmo lançamento manual.
    copias = []
    for arquivo in arquivos:
        arquivo.seek(0)
        conteudo = arquivo.read()
        copias.append((arquivo.name, conteudo, len(conteudo)))

    criados = 0
    for titulo in titulos:
        existentes = {}
        if titulo.arquivo_documento and titulo.arquivo_documento.name:
            nome_legacy = titulo.arquivo_documento.name.rsplit("/", 1)[-1].strip().lower()
            try:
                tamanho_legacy = titulo.arquivo_documento.size
            except (FileNotFoundError, OSError):
                tamanho_legacy = None
            existentes.setdefault(nome_legacy, set()).add(tamanho_legacy)

        for anexo_existente in titulo.anexos.all():
            nome = (anexo_existente.nome_original or anexo_existente.arquivo.name.rsplit("/", 1)[-1]).strip().lower()
            try:
                tamanho = anexo_existente.arquivo.size
            except (FileNotFoundError, OSError):
                tamanho = None
            existentes.setdefault(nome, set()).add(tamanho)

        for nome, conteudo, tamanho in copias:
            chave_nome = (nome or "").strip().lower()
            if tamanho in existentes.get(chave_nome, set()):
                continue

            anexo = AnexoTituloPagar(
                titulo=titulo,
                nome_original=nome,
                enviado_por=usuario,
            )
            anexo.arquivo.save(nome, ContentFile(conteudo), save=False)
            anexo.save()
            existentes.setdefault(chave_nome, set()).add(tamanho)
            criados += 1

    return criados


def _documentos_pedido(titulo):
    if not titulo.pedido_id:
        return [], []
    anexos = list(titulo.pedido.anexos.all())
    notas_fiscais = [
        recebimento
        for recebimento in titulo.pedido.recebimentos.all()
        if recebimento.arquivo_nota_fiscal and recebimento.arquivo_nota_fiscal.name
    ]
    return anexos, notas_fiscais

@login_required
@never_cache
@require_http_methods(["GET"])
def titulo_catalogo(request):
    tipo = request.GET.get("tipo")
    if tipo == "fornecedor_publico":
        permitido = possui_acao_financeiro(request.user, "VISUALIZAR")
    else:
        permitido = any(possui_acao_financeiro(request.user, acao) for acao in ("LANCAR_TITULOS", "EDITAR_TITULOS"))
    if not permitido:
        raise PermissionDenied

    if tipo == "dados_bancarios":
        fornecedor = get_object_or_404(Fornecedor.objects.only(
            "documento", "banco", "agencia", "conta_corrente", "operacao_bancaria", "pix", "titular_conta",
        ), ativo=True, pk=_inteiro_positivo(request.GET.get("id")))
        return JsonResponse({
            "documento": fornecedor.documento or "", "banco": fornecedor.banco or "",
            "agencia": fornecedor.agencia or "", "conta_corrente": fornecedor.conta_corrente or "",
            "operacao": fornecedor.operacao_bancaria or "", "pix": fornecedor.pix or "", "titular": fornecedor.titular_conta or "",
        })

    busca = (request.GET.get("q") or "").strip()[:100]
    if tipo in {"fornecedor", "fornecedor_publico"}:
        itens = Fornecedor.objects.only("codigo", "nome", "nome_fantasia").filter(
            Q(nome__icontains=busca) | Q(nome_fantasia__icontains=busca) | Q(codigo__icontains=busca),
        ).order_by("nome", "pk")
    elif tipo == "obra":
        itens = Obra.objects.only("codigo", "nome").filter(Q(nome__icontains=busca) | Q(codigo__icontains=busca)).order_by("nome", "pk")
    elif tipo == "material":
        itens = Material.objects.select_related("unidade").only("codigo", "nome", "especificacao", "unidade__sigla").filter(
            Q(nome__icontains=busca) | Q(especificacao__icontains=busca) | Q(codigo__icontains=busca),
        ).order_by("nome", "especificacao", "pk")
    elif tipo == "apropriacao":
        itens = PlanoFinanceiro.objects.only("codigo", "nome").filter(ativo=True, pai__isnull=False).filter(
            Q(codigo__icontains=busca) | Q(nome__icontains=busca) | Q(pai__nome__icontains=busca),
        ).order_by("pai__codigo", "codigo", "nome", "pk")
    else:
        raise Http404
    return JsonResponse({"resultados": [
        {"id": item.pk, "texto": item.nome_exibicao if tipo == "fornecedor_publico" else str(item)} for item in itens[:25]
    ]})


@financeiro_acao_required("VISUALIZAR")
def titulos_lista(request):
    from financeiro.views.agenda import contexto_contas_a_pagar

    return render(request, "financeiro/titulos_lista.html", contexto_contas_a_pagar(request, timezone.localdate()))


@financeiro_acao_required("LANCAR_TITULOS")
@never_cache
@require_http_methods(["GET", "POST"])
def titulo_novo(request):
    status = 200
    if request.method == "POST":
        form = SolicitacaoAvulsaForm(request.POST, request.FILES, usuario=request.user)

        def validar_dados():
            nonlocal form
            # Uma tentativa de validação interrompida pelo banco não deixa cache parcial.
            form = SolicitacaoAvulsaForm(request.POST, request.FILES, usuario=request.user)
            if not form.is_valid():
                raise SolicitacaoAvulsaInvalida
            return {nome: valor for nome, valor in form.cleaned_data.items() if nome != "chave_idempotencia"}

        try:
            chave = form.chave_da_tentativa()
            titulos, criados = registrar_solicitacao_avulsa(
                usuario=request.user,
                chave=chave,
                impressao=form.impressao_da_tentativa(),
                validar_dados=validar_dados,
            )
        except ValidationError as exc:
            form.add_error(None if hasattr(exc, "error_dict") else "chave_idempotencia", exc)
            status = 400
        except SolicitacaoAvulsaInvalida:
            pass
        except SolicitacaoAvulsaDivergente:
            form.add_error("chave_idempotencia", "Esta tentativa já foi enviada com dados diferentes. Abra uma nova solicitação para criar outra conta.")
            status = 409
        else:
            if not criados:
                messages.info(request, "Esta solicitação já foi registrada.")
            if len(titulos) == 1:
                if criados:
                    messages.success(request, f"Conta {titulos[0].numero} criada e enviada para aprovação.")
                return redirect("financeiro:titulo_detalhe", pk=titulos[0].pk)
            if criados:
                messages.success(request, f"{len(titulos)} parcelas criadas e enviadas para aprovação.")
            if titulos:
                return redirect(f"{reverse('financeiro:titulos')}?solicitacao={titulos[0].solicitacao_avulsa_id}")
            return redirect("financeiro:titulos")
    else:
        form = SolicitacaoAvulsaForm(usuario=request.user)
    return render(request, "financeiro/titulo_form.html", {
        "form": form,
        "modo": "novo",
    }, status=status)


@financeiro_acao_required("VISUALIZAR")
def titulo_detalhe(request, pk):
    titulo = get_object_or_404(
        TituloPagar.objects.select_related(
            "fornecedor", "obra", "plano_financeiro", "pedido", "recebimento", "previsao_origem", "pagamento"
        ).prefetch_related("aprovacoes__usuario", "historico__usuario", "materiais", "anexos", "pedido__anexos", "pedido__recebimentos"),
        pk=pk,
    )
    recebimentos = []
    valor_documentado = Decimal("0")
    if titulo.pedido_id:
        recebimentos = list(titulo.pedido.recebimentos.prefetch_related("itens").all())
        valor_documentado = sum((r.valor_total_nota or Decimal("0") for r in recebimentos), Decimal("0"))

    anexos_pedido, notas_fiscais_pedido = _documentos_pedido(titulo)

    return render(request, "financeiro/titulo_detalhe.html", {
        "titulo": titulo,
        "recebimentos": recebimentos,
        "anexos_pedido": anexos_pedido,
        "notas_fiscais_pedido": notas_fiscais_pedido,
        "valor_documentado_pedido": valor_documentado,
        "pode_editar": possui_acao_financeiro(request.user, "EDITAR_TITULOS"),
        "pode_aprovar": possui_acao_financeiro(request.user, "APROVAR"),
        "pode_pagar": possui_acao_financeiro(request.user, "PAGAR"),
    })


@financeiro_acao_required("EDITAR_TITULOS")
def titulo_editar(request, pk):
    titulo = get_object_or_404(
        TituloPagar.objects.select_related("fornecedor", "pedido").prefetch_related("anexos", "pedido__anexos", "pedido__recebimentos"),
        pk=pk,
    )
    if titulo.esta_pago:
        messages.error(request, "Conta paga não pode ser editada. Estorne o pagamento primeiro.")
        return redirect("financeiro:titulo_detalhe", pk=pk)

    if request.method == "POST":
        form = TituloPagarForm(request.POST, request.FILES, instance=titulo, titulo_integrado=titulo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            anexos = dados.pop("anexos", [])
            try:
                titulo = atualizar_titulo(titulo, usuario=request.user, dados=dados)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("financeiro:titulo_detalhe", pk=pk)
            _salvar_anexos([titulo], anexos, request.user)
            messages.success(request, "Conta a Pagar atualizada.")
            return redirect("financeiro:titulo_detalhe", pk=titulo.pk)
    else:
        form = TituloPagarForm(instance=titulo, titulo_integrado=titulo)
    anexos_pedido, notas_fiscais_pedido = _documentos_pedido(titulo)
    return render(request, "financeiro/titulo_form.html", {
        "form": form,
        "modo": "editar",
        "titulo": titulo,
        "anexos_pedido": anexos_pedido,
        "notas_fiscais_pedido": notas_fiscais_pedido,
    })


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_excluir_anexo(request, pk, anexo_pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    if titulo.esta_pago:
        messages.error(request, "Conta paga não pode ter anexos excluídos. Estorne o pagamento primeiro.")
        return redirect("financeiro:titulo_detalhe", pk=pk)

    anexo = get_object_or_404(AnexoTituloPagar, pk=anexo_pk, titulo=titulo)
    nome = anexo.nome_original or anexo.arquivo.name.rsplit("/", 1)[-1]
    arquivo = anexo.arquivo
    anexo.delete()
    try:
        arquivo.delete(save=False)
    except (FileNotFoundError, OSError):
        pass
    messages.success(request, f"Anexo {nome} excluído.")
    return redirect("financeiro:titulo_editar", pk=pk)


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_excluir_documento_legacy(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    if titulo.esta_pago:
        messages.error(request, "Conta paga não pode ter documentos excluídos. Estorne o pagamento primeiro.")
        return redirect("financeiro:titulo_detalhe", pk=pk)
    if not titulo.arquivo_documento:
        messages.info(request, "Esta conta não possui documento anterior para excluir.")
        return redirect("financeiro:titulo_editar", pk=pk)

    arquivo = titulo.arquivo_documento
    titulo.arquivo_documento = None
    titulo.save(update_fields=["arquivo_documento", "atualizado_em"])
    try:
        arquivo.delete(save=False)
    except (FileNotFoundError, OSError):
        pass
    messages.success(request, "Documento anterior excluído.")
    return redirect("financeiro:titulo_editar", pk=pk)


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_enviar_aprovacao(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    try:
        titulo = enviar_para_aprovacao(titulo, usuario=request.user)
        if titulo.status == TituloPagar.Status.APROVADO:
            messages.info(request, "A conta já está aprovada.")
        else:
            messages.success(request, "Conta aguardando aprovação.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("financeiro:titulo_detalhe", pk=pk)


@financeiro_acao_required("APROVAR")
@require_POST
def titulo_decidir(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    decisao = request.POST.get("decisao")
    observacao = (request.POST.get("observacao") or "").strip()
    if decisao not in {AprovacaoTituloFinanceiro.Decisao.APROVADO, AprovacaoTituloFinanceiro.Decisao.REJEITADO}:
        messages.error(request, "Decisão inválida.")
        return redirect("financeiro:titulo_detalhe", pk=pk)
    try:
        decidir_titulo(titulo, usuario=request.user, decisao=decisao, observacao=observacao)
        messages.success(request, "Decisão registrada.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("financeiro:titulo_detalhe", pk=pk)


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_configurar(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    # Depois de um pagamento efetivado, dados financeiros da conta ficam
    # imutáveis até que o pagamento seja estornado. Usamos esta_pago em vez de
    # testar somente o status para também proteger eventuais dados legados em
    # que exista pagamento efetivado antes da sincronização do status.
    if titulo.esta_pago:
        messages.error(
            request,
            "Conta paga não pode ter apropriação ou vencimento alterados. "
            "Estorne o pagamento primeiro."
        )
        return redirect("financeiro:titulos")

    apropriacao_id = (request.POST.get("apropriacao") or "").strip()
    vencimento_txt = (request.POST.get("vencimento") or "").strip()
    dados = {}

    if apropriacao_id:
        apropriacao = get_object_or_404(PlanoFinanceiro, pk=apropriacao_id, ativo=True, pai__isnull=False)
        dados["plano_financeiro"] = apropriacao

    if titulo.origem != TituloPagar.Origem.GRANDE_FORNECEDOR:
        from django.utils.dateparse import parse_date
        vencimento = parse_date(vencimento_txt) if vencimento_txt else None
        if vencimento:
            dados["vencimento"] = vencimento

    if not dados:
        messages.warning(request, "Nenhuma alteração informada.")
        return redirect("financeiro:titulos")

    try:
        titulo = atualizar_titulo(titulo, usuario=request.user, dados=dados, motivo="Vencimento/apropriação ajustados na lista de Contas a Pagar.")
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("financeiro:titulos")

    # Na operação diária, salvar o vencimento já conclui a preparação da conta.
    # Se todos os requisitos estiverem preenchidos, ela segue automaticamente
    # para aprovação sem exigir um segundo botão/segunda etapa.
    if titulo.status not in {
        TituloPagar.Status.AGUARDANDO_APROVACAO,
        TituloPagar.Status.APROVADO,
        TituloPagar.Status.PAGO,
        TituloPagar.Status.CANCELADO,
    }:
        try:
            titulo = enviar_para_aprovacao(titulo, usuario=request.user)
            if titulo.status == TituloPagar.Status.APROVADO:
                messages.success(request, f"Conta {titulo.numero} atualizada.")
            else:
                messages.success(request, f"Conta {titulo.numero} atualizada e enviada para aprovação.")
        except ValidationError as exc:
            messages.warning(request, f"Conta {titulo.numero} salva, mas ainda não foi enviada: {'; '.join(exc.messages)}")
    else:
        messages.success(request, f"Conta {titulo.numero} atualizada.")
    return redirect("financeiro:titulos")


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_cancelar(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    try:
        cancelar_titulo(titulo, usuario=request.user, motivo=(request.POST.get("motivo") or "").strip())
        messages.success(request, "Conta cancelada.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("financeiro:titulo_detalhe", pk=pk)
