from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from planejamento.models import (
    AtividadePlanejamento,
    ImportacaoCronograma,
    InsumoPlanejamento,
    SuprimentoAtividade,
)
from planejamento.services.cronograma import (
    ImportacaoCronogramaError,
    importar_cronograma,
    montar_painel_cronograma,
)
from planejamento.services.cronograma.consultas import (
    CronogramaBaseError,
)


# ============================================================
# HELPERS DE NAVEGAÇÃO / FORMULÁRIOS
# ============================================================


def _redirect_painel(
    *,
    projeto: str | None = None,
    semana: int | str | None = None,
    ancora: str | None = "disciplinas",
):
    """
    Volta ao painel preservando obra/semana.

    As operações de suprimentos acontecem na própria experiência do
    cronograma, portanto após POST o usuário retorna ao mesmo filtro.
    """
    url = reverse("planejamento:painel_cronograma")

    parametros = {}

    if projeto:
        parametros["projeto"] = projeto

    if semana not in (None, ""):
        parametros["semana"] = semana

    if parametros:
        url = f"{url}?{urlencode(parametros)}"

    if ancora:
        url = f"{url}#{ancora}"

    return redirect(url)


def _contexto_retorno(request) -> tuple[str | None, str | None]:
    projeto = (
        request.POST.get("projeto")
        or request.GET.get("projeto")
        or ""
    ).strip()

    semana = (
        request.POST.get("semana")
        or request.GET.get("semana")
        or ""
    ).strip()

    return projeto or None, semana or None


def _decimal_form(
    valor: str | None,
    *,
    campo: str,
    permitir_zero: bool = True,
) -> Decimal:
    """
    Converte valores vindos de input number ou texto em Decimal.

    Aceita:
    - 1234.56
    - 1234,56
    - R$ 1234,56
    """
    texto = (valor or "").strip()

    if not texto:
        raise ValueError(f"Informe {campo}.")

    texto = (
        texto
        .replace("R$", "")
        .replace(" ", "")
    )

    # Se vier no padrão brasileiro 1.234,56.
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(
            f"{campo.capitalize()} inválido."
        ) from exc

    if numero < 0:
        raise ValueError(
            f"{campo.capitalize()} não pode ser negativo."
        )

    if not permitir_zero and numero == 0:
        raise ValueError(
            f"{campo.capitalize()} deve ser maior que zero."
        )

    return numero


def _data_form(valor: str | None):
    texto = (valor or "").strip()

    if not texto:
        return None

    try:
        return datetime.strptime(
            texto,
            "%Y-%m-%d",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "Data limite para compra inválida."
        ) from exc


def _unidades_validas() -> set[str]:
    return {
        valor
        for valor, _rotulo
        in InsumoPlanejamento.UnidadeMedida.choices
    }


def _validar_unidade(
    unidade: str | None,
    *,
    obrigatoria: bool = True,
) -> str:
    unidade = (unidade or "").strip().upper()

    if not unidade and not obrigatoria:
        return ""

    if unidade not in _unidades_validas():
        raise ValueError(
            "Selecione uma unidade de medida válida."
        )

    return unidade


def _obter_ou_criar_insumo_inline(
    *,
    request,
    insumo_id: str | None,
    novo_nome: str | None,
    nova_unidade: str | None,
):
    """
    Permite usar um insumo existente ou criar um novo diretamente
    no modal de suprimento.
    """
    if insumo_id:
        return get_object_or_404(
            InsumoPlanejamento,
            id=insumo_id,
            ativo=True,
        )

    nome = (novo_nome or "").strip()

    if not nome:
        raise ValueError(
            "Selecione um insumo ou informe um novo insumo."
        )

    unidade = _validar_unidade(
        nova_unidade,
        obrigatoria=True,
    )

    existente = (
        InsumoPlanejamento.objects
        .filter(nome__iexact=nome)
        .first()
    )

    if existente is not None:
        campos_atualizar = []

        if not existente.ativo:
            existente.ativo = True
            campos_atualizar.append("ativo")

        if (
            not existente.unidade_padrao
            and unidade
        ):
            existente.unidade_padrao = unidade
            campos_atualizar.append("unidade_padrao")

        if campos_atualizar:
            campos_atualizar.append("atualizado_em")
            existente.save(
                update_fields=campos_atualizar
            )

        return existente

    return InsumoPlanejamento.objects.create(
        nome=nome,
        unidade_padrao=unidade,
        criado_por=request.user,
    )


# ============================================================
# PAINEL PRINCIPAL
# ============================================================


@login_required
def painel_cronograma(request):
    projeto = (
        request.GET.get("projeto") or ""
    ).strip()

    semana_texto = (
        request.GET.get("semana") or ""
    ).strip()

    try:
        semana = (
            int(semana_texto)
            if semana_texto
            else None
        )
    except (TypeError, ValueError):
        semana = None

    try:
        contexto = montar_painel_cronograma(
            projeto=projeto or None,
            semana=semana,
        )
    except CronogramaBaseError as exc:
        contexto = {
            "projetos": [],
            "projeto_selecionado": None,
            "semanas": [],
            "semana_selecionada": None,
            "semana_solicitada": semana,
            "possui_dados": False,
            "resumo": None,
            "serie": [],
            "avancos": [],
            "medias": None,
            "prazos": None,
            "marcos": [],
            "contadores_atividades": {},
            "atividades_prioritarias": [],
            "programacao_semana": {},
            "resumo_prioridades": {},
            "disciplinas": [],
            "checklists": {
                "habitese": {},
                "pos_habitese": {},
            },
            "orcamento_suprimentos": {
                "valor_total": Decimal("0"),
                "quantidade_insumos": 0,
                "quantidade_atividades": 0,
                "quantidade_atividades_com_suprimentos": 0,
                "quantidade_atividades_sem_suprimentos": 0,
                "disciplinas": [],
                "por_disciplina": {},
                "por_atividade": {},
            },
            "alertas_painel": [],
            "erro_base": str(exc),
            "importacao_ativa": None,
        }

    # Dados auxiliares para os modais de suprimentos da mesma tela.
    contexto["insumos_planejamento"] = list(
        InsumoPlanejamento.objects
        .filter(ativo=True)
        .order_by("nome")
    )

    contexto["unidades_medida_suprimentos"] = (
        InsumoPlanejamento.UnidadeMedida.choices
    )

    return render(
        request,
        "planejamento/painel_cronograma.html",
        contexto,
    )


# ============================================================
# CATÁLOGO DE INSUMOS
# ============================================================


@login_required
@require_POST
def cadastrar_insumo_planejamento(request):
    projeto, semana = _contexto_retorno(request)

    nome = (
        request.POST.get("nome")
        or ""
    ).strip()

    descricao = (
        request.POST.get("descricao")
        or ""
    ).strip()

    try:
        if not nome:
            raise ValueError(
                "Informe o nome do insumo."
            )

        unidade = _validar_unidade(
            request.POST.get("unidade_padrao"),
            obrigatoria=True,
        )

        existente = (
            InsumoPlanejamento.objects
            .filter(nome__iexact=nome)
            .first()
        )

        if existente is not None:
            if existente.ativo:
                raise ValueError(
                    "Já existe um insumo com esse nome."
                )

            existente.ativo = True
            existente.unidade_padrao = unidade
            existente.descricao = descricao
            existente.save(
                update_fields=[
                    "ativo",
                    "unidade_padrao",
                    "descricao",
                    "atualizado_em",
                ]
            )

            messages.success(
                request,
                f"Insumo “{existente.nome}” reativado com sucesso.",
            )
        else:
            insumo = InsumoPlanejamento.objects.create(
                nome=nome,
                unidade_padrao=unidade,
                descricao=descricao,
                criado_por=request.user,
            )

            messages.success(
                request,
                f"Insumo “{insumo.nome}” cadastrado com sucesso.",
            )

    except ValueError as exc:
        messages.error(
            request,
            str(exc),
        )

    return _redirect_painel(
        projeto=projeto,
        semana=semana,
    )


@login_required
@require_POST
def editar_insumo_planejamento(
    request,
    insumo_id: int,
):
    projeto, semana = _contexto_retorno(request)

    insumo = get_object_or_404(
        InsumoPlanejamento,
        id=insumo_id,
    )

    try:
        nome = (
            request.POST.get("nome")
            or ""
        ).strip()

        if not nome:
            raise ValueError(
                "Informe o nome do insumo."
            )

        unidade = _validar_unidade(
            request.POST.get("unidade_padrao"),
            obrigatoria=True,
        )

        duplicado = (
            InsumoPlanejamento.objects
            .filter(nome__iexact=nome)
            .exclude(id=insumo.id)
            .exists()
        )

        if duplicado:
            raise ValueError(
                "Já existe outro insumo com esse nome."
            )

        insumo.nome = nome
        insumo.unidade_padrao = unidade
        insumo.descricao = (
            request.POST.get("descricao")
            or ""
        ).strip()
        insumo.save()

        messages.success(
            request,
            f"Insumo “{insumo.nome}” atualizado.",
        )

    except ValueError as exc:
        messages.error(
            request,
            str(exc),
        )

    return _redirect_painel(
        projeto=projeto,
        semana=semana,
    )


@login_required
@require_POST
def desativar_insumo_planejamento(
    request,
    insumo_id: int,
):
    projeto, semana = _contexto_retorno(request)

    insumo = get_object_or_404(
        InsumoPlanejamento,
        id=insumo_id,
    )

    possui_vinculos_ativos = (
        SuprimentoAtividade.objects
        .filter(
            insumo=insumo,
            ativo=True,
        )
        .exists()
    )

    if possui_vinculos_ativos:
        messages.error(
            request,
            "Este insumo não pode ser desativado enquanto estiver "
            "vinculado a suprimentos ativos de atividades.",
        )
    else:
        insumo.ativo = False
        insumo.save(
            update_fields=[
                "ativo",
                "atualizado_em",
            ]
        )

        messages.success(
            request,
            f"Insumo “{insumo.nome}” desativado.",
        )

    return _redirect_painel(
        projeto=projeto,
        semana=semana,
    )


# ============================================================
# ORÇAMENTO / SUPRIMENTOS DAS ATIVIDADES
# ============================================================


@login_required
@require_POST
def adicionar_suprimento_atividade(
    request,
    atividade_id: int,
):
    projeto, semana = _contexto_retorno(request)

    atividade = get_object_or_404(
        AtividadePlanejamento.objects.select_related(
            "obra"
        ),
        id=atividade_id,
        ativa=True,
    )

    try:
        with transaction.atomic():
            insumo = _obter_ou_criar_insumo_inline(
                request=request,
                insumo_id=(
                    request.POST.get("insumo_id")
                    or ""
                ).strip() or None,
                novo_nome=request.POST.get(
                    "novo_insumo_nome"
                ),
                nova_unidade=request.POST.get(
                    "novo_insumo_unidade"
                ),
            )

            unidade = _validar_unidade(
                request.POST.get("unidade_medida")
                or insumo.unidade_padrao,
                obrigatoria=True,
            )

            quantidade = _decimal_form(
                request.POST.get("quantidade"),
                campo="a quantidade",
                permitir_zero=False,
            )

            valor_unitario = _decimal_form(
                request.POST.get("valor_unitario"),
                campo="o valor unitário",
                permitir_zero=True,
            )

            data_limite_compra = _data_form(
                request.POST.get(
                    "data_limite_compra"
                )
            )

            suprimento = (
                SuprimentoAtividade.objects.create(
                    atividade=atividade,
                    insumo=insumo,
                    quantidade=quantidade,
                    unidade_medida=unidade,
                    valor_unitario=valor_unitario,
                    data_limite_compra=data_limite_compra,
                    observacao=(
                        request.POST.get("observacao")
                        or ""
                    ).strip(),
                    criado_por=request.user,
                )
            )

        messages.success(
            request,
            (
                f"Suprimento “{suprimento.insumo.nome}” adicionado "
                f"à atividade “{atividade.nome_tarefa}”."
            ),
        )

    except ValueError as exc:
        messages.error(
            request,
            str(exc),
        )

    return _redirect_painel(
        projeto=projeto or atividade.projeto_origem,
        semana=semana,
        ancora=f"atividade-{atividade.id}",
    )


@login_required
@require_POST
def editar_suprimento_atividade(
    request,
    suprimento_id: int,
):
    projeto, semana = _contexto_retorno(request)

    suprimento = get_object_or_404(
        SuprimentoAtividade.objects
        .select_related(
            "atividade",
            "insumo",
        ),
        id=suprimento_id,
        ativo=True,
    )

    atividade = suprimento.atividade

    try:
        with transaction.atomic():
            insumo_id = (
                request.POST.get("insumo_id")
                or ""
            ).strip()

            if insumo_id:
                suprimento.insumo = get_object_or_404(
                    InsumoPlanejamento,
                    id=insumo_id,
                    ativo=True,
                )

            suprimento.unidade_medida = _validar_unidade(
                request.POST.get("unidade_medida")
                or suprimento.insumo.unidade_padrao,
                obrigatoria=True,
            )

            suprimento.quantidade = _decimal_form(
                request.POST.get("quantidade"),
                campo="a quantidade",
                permitir_zero=False,
            )

            suprimento.valor_unitario = _decimal_form(
                request.POST.get("valor_unitario"),
                campo="o valor unitário",
                permitir_zero=True,
            )

            suprimento.data_limite_compra = _data_form(
                request.POST.get(
                    "data_limite_compra"
                )
            )

            suprimento.observacao = (
                request.POST.get("observacao")
                or ""
            ).strip()

            suprimento.save()

        messages.success(
            request,
            "Suprimento atualizado com sucesso.",
        )

    except ValueError as exc:
        messages.error(
            request,
            str(exc),
        )

    return _redirect_painel(
        projeto=projeto or atividade.projeto_origem,
        semana=semana,
        ancora=f"atividade-{atividade.id}",
    )


@login_required
@require_POST
def excluir_suprimento_atividade(
    request,
    suprimento_id: int,
):
    """
    Exclusão lógica.

    O registro permanece no banco para auditoria e futuras integrações
    com compras/orçamento realizado.
    """
    projeto, semana = _contexto_retorno(request)

    suprimento = get_object_or_404(
        SuprimentoAtividade.objects
        .select_related(
            "atividade",
            "insumo",
        ),
        id=suprimento_id,
        ativo=True,
    )

    atividade = suprimento.atividade
    nome_insumo = suprimento.insumo.nome

    suprimento.ativo = False
    suprimento.save(
        update_fields=[
            "ativo",
            "atualizado_em",
        ]
    )

    messages.success(
        request,
        f"Suprimento “{nome_insumo}” removido da atividade.",
    )

    return _redirect_painel(
        projeto=projeto or atividade.projeto_origem,
        semana=semana,
        ancora=f"atividade-{atividade.id}",
    )


# ============================================================
# IMPORTAÇÕES DO CRONOGRAMA
# ============================================================


@login_required
def historico_importacoes_cronograma(request):
    importacoes = (
        ImportacaoCronograma.objects
        .select_related("executado_por")
        .order_by("-criado_em")[:50]
    )

    return render(
        request,
        "planejamento/importacoes_cronograma.html",
        {"importacoes": importacoes},
    )


@login_required
@require_POST
def atualizar_cronograma(request):
    if not request.user.is_superuser:
        messages.error(
            request,
            "Você não tem permissão para atualizar o cronograma.",
        )
        return redirect(
            "planejamento:painel_cronograma"
        )

    try:
        resultado = importar_cronograma(
            executado_por=request.user,
            forcar=(
                request.POST.get("forcar") == "1"
            ),
        )
    except ImportacaoCronogramaError as exc:
        messages.error(
            request,
            "Não foi possível atualizar o cronograma: "
            f"{exc}",
        )
    else:
        if resultado.importado:
            messages.success(
                request,
                resultado.mensagem,
            )
        else:
            messages.info(
                request,
                resultado.mensagem,
            )

    return redirect(
        "planejamento:painel_cronograma"
    )
