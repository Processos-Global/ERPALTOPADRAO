from django.urls import reverse

from usuarios.models import AcaoCompra, TipoNotificacao
from usuarios.services.notificacoes import (
    marcar_chave_como_lida,
    notificar_usuarios_com_acao_compras,
)


def _url_processo(processo, aba):
    return f"{reverse('compras:detalhe_processo', args=[processo.pk])}#{aba}"


def chave_cotacao_processo(processo):
    return f"compras:cotacao:processo:{processo.pk}"


def chave_compatibilizacao(cotacao):
    return f"compras:compatibilizacao:cotacao:{cotacao.pk}"


def chave_negociacao(cotacao):
    return f"compras:negociacao:cotacao:{cotacao.pk}"


def chave_aprovacao(cotacao):
    return f"compras:aprovacao:cotacao:{cotacao.pk}"


def notificar_novo_processo_para_cotacao(processo):
    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.COTAR,
        titulo="Nova compra aguardando cotação",
        mensagem=f"O processo {processo.numero} foi aberto e está pronto para cotação.",
        evento="PROCESSO_AGUARDANDO_COTACAO",
        url=_url_processo(processo, "cotacao"),
        chave_unica=chave_cotacao_processo(processo),
        dados={"processo_id": processo.pk},
        tipo=TipoNotificacao.ACAO,
    )


def notificar_proposta_para_compatibilizacao(cotacao):
    marcar_chave_como_lida(chave_negociacao(cotacao))
    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.COMPATIBILIZAR,
        titulo="Compatibilização necessária",
        mensagem=(
            f"A proposta de {cotacao.fornecedor.nome} no processo "
            f"{cotacao.processo.numero} aguarda análise técnica."
        ),
        evento="PROPOSTA_ENVIADA_COMPATIBILIZACAO",
        url=_url_processo(cotacao.processo, "comparacao"),
        chave_unica=chave_compatibilizacao(cotacao),
        dados={
            "processo_id": cotacao.processo_id,
            "cotacao_id": cotacao.pk,
            "fornecedor_id": cotacao.fornecedor_id,
        },
        tipo=TipoNotificacao.ACAO,
    )


def notificar_proposta_para_negociacao(cotacao):
    marcar_chave_como_lida(chave_compatibilizacao(cotacao))
    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.NEGOCIAR,
        titulo="Proposta disponível para negociação",
        mensagem=(
            f"A proposta de {cotacao.fornecedor.nome} no processo "
            f"{cotacao.processo.numero} foi liberada para negociação comercial."
        ),
        evento="PROPOSTA_ENVIADA_NEGOCIACAO",
        url=_url_processo(cotacao.processo, "negociacao"),
        chave_unica=chave_negociacao(cotacao),
        dados={
            "processo_id": cotacao.processo_id,
            "cotacao_id": cotacao.pk,
            "fornecedor_id": cotacao.fornecedor_id,
        },
        tipo=TipoNotificacao.ACAO,
    )


def notificar_proposta_para_aprovacao(cotacao):
    marcar_chave_como_lida(chave_negociacao(cotacao))
    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.APROVAR,
        titulo="Aprovação necessária",
        mensagem=(
            f"A proposta de {cotacao.fornecedor.nome} no processo "
            f"{cotacao.processo.numero} foi enviada para aprovação."
        ),
        evento="PROPOSTA_ENVIADA_APROVACAO",
        url=_url_processo(cotacao.processo, "aprovacao"),
        chave_unica=chave_aprovacao(cotacao),
        dados={
            "processo_id": cotacao.processo_id,
            "cotacao_id": cotacao.pk,
            "fornecedor_id": cotacao.fornecedor_id,
        },
        tipo=TipoNotificacao.ACAO,
    )


def notificar_proposta_devolvida_negociacao(cotacao):
    marcar_chave_como_lida(chave_aprovacao(cotacao))
    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.NEGOCIAR,
        titulo="Proposta devolvida para negociação",
        mensagem=(
            f"O gestor devolveu a proposta de {cotacao.fornecedor.nome} do processo "
            f"{cotacao.processo.numero} para ajuste comercial."
        ),
        evento="PROPOSTA_DEVOLVIDA_NEGOCIACAO",
        url=_url_processo(cotacao.processo, "negociacao"),
        chave_unica=chave_negociacao(cotacao),
        dados={
            "processo_id": cotacao.processo_id,
            "cotacao_id": cotacao.pk,
            "fornecedor_id": cotacao.fornecedor_id,
        },
        tipo=TipoNotificacao.ACAO,
    )


def notificar_ajuste_solicitado(processo):
    for cotacao in processo.cotacoes.filter(enviada_negociacao_em__isnull=False):
        marcar_chave_como_lida(chave_aprovacao(cotacao))

    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.NEGOCIAR,
        titulo="Ajuste solicitado pelo gestor",
        mensagem=f"O processo {processo.numero} retornou para negociação e precisa de ajustes.",
        evento="AJUSTE_SOLICITADO_GESTOR",
        url=_url_processo(processo, "negociacao"),
        chave_unica=f"compras:ajuste-gestor:processo:{processo.pk}",
        dados={"processo_id": processo.pk},
        tipo=TipoNotificacao.ACAO,
    )


def notificar_processo_reprovado(processo):
    for cotacao in processo.cotacoes.all():
        marcar_chave_como_lida(chave_aprovacao(cotacao))

    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.NEGOCIAR,
        titulo="Compra reprovada pelo gestor",
        mensagem=f"O processo {processo.numero} foi reprovado e encerrado sem geração de pedido.",
        evento="PROCESSO_REPROVADO",
        url=_url_processo(processo, "aprovacao"),
        chave_unica=f"compras:reprovado:processo:{processo.pk}",
        dados={"processo_id": processo.pk},
        tipo=TipoNotificacao.ATENCAO,
    )


def notificar_pedidos_gerados(processo, quantidade):
    for cotacao in processo.cotacoes.all():
        marcar_chave_como_lida(chave_aprovacao(cotacao))

    return notificar_usuarios_com_acao_compras(
        acao=AcaoCompra.GERENCIAR_PEDIDOS,
        titulo="Pedidos gerados",
        mensagem=(
            f"O processo {processo.numero} foi aprovado e gerou "
            f"{quantidade} pedido(s) automaticamente."
        ),
        evento="PEDIDOS_GERADOS_APROVACAO",
        url=_url_processo(processo, "pedido"),
        chave_unica=f"compras:pedidos-gerados:processo:{processo.pk}",
        dados={"processo_id": processo.pk, "quantidade_pedidos": quantidade},
        tipo=TipoNotificacao.SUCESSO,
    )

def notificar_retorno_etapa(processo):
    if processo.etapa_atual == processo.Etapa.NEGOCIACAO:
        for cotacao in processo.cotacoes.all():
            marcar_chave_como_lida(chave_aprovacao(cotacao))
        acao = AcaoCompra.NEGOCIAR
        titulo = "Processo retornado para negociação"
        mensagem = f"O processo {processo.numero} retornou para a etapa de negociação."
        aba = "negociacao"
    elif processo.etapa_atual == processo.Etapa.COMPATIBILIZACAO:
        acao = AcaoCompra.COMPATIBILIZAR
        titulo = "Processo retornado para compatibilização"
        mensagem = f"O processo {processo.numero} retornou para análise técnica."
        aba = "comparacao"
    elif processo.etapa_atual == processo.Etapa.COTACAO:
        acao = AcaoCompra.COTAR
        titulo = "Processo retornado para cotação"
        mensagem = f"O processo {processo.numero} retornou para a etapa de cotação."
        aba = "cotacao"
    else:
        return []

    return notificar_usuarios_com_acao_compras(
        acao=acao,
        titulo=titulo,
        mensagem=mensagem,
        evento="PROCESSO_RETORNOU_ETAPA",
        url=_url_processo(processo, aba),
        chave_unica=f"compras:retorno:{processo.etapa_atual}:processo:{processo.pk}",
        dados={"processo_id": processo.pk, "etapa": processo.etapa_atual},
        tipo=TipoNotificacao.ACAO,
    )

