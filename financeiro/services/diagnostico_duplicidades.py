import re
from collections import defaultdict
from datetime import timedelta

from django.db.models import Prefetch

from financeiro.models import AnexoTituloPagar, AprovacaoTituloFinanceiro, HistoricoTituloFinanceiro, TituloPagar


JANELA_SUSPEITA = timedelta(minutes=10)
CLASSIFICACOES = {
    "confirmada": ("Duplicidade tecnicamente confirmada", "Confira o identificador de origem e os registros vinculados antes de qualquer ajuste."),
    "forte": ("Forte suspeita", "Confronte a solicitação original, as aprovações, os documentos e os pagamentos dos títulos."),
    "possivel": ("Possível coincidência", "Confirme com o responsável se os títulos representam obrigações distintas."),
    "semelhante": ("Solicitações semelhantes legítimas", "Confirme a correspondência de cada parcela ou documento com sua obrigação."),
}


def _normalizar(texto):
    return " ".join((texto or "").casefold().split())


def _mesma_obrigacao(titulo):
    beneficiario = titulo.fornecedor_id or _normalizar(titulo.beneficiario_nome)
    return (
        titulo.obra_id, beneficiario, titulo.valor_original, titulo.valor_liquido,
        titulo.vencimento, _normalizar(titulo.descricao), titulo.origem,
    )


def _identificadores(titulo):
    if titulo.solicitacao_avulsa_id and titulo.parcela_ordem:
        yield "tentativa e ordem da parcela", titulo.solicitacao_avulsa_id, titulo.parcela_ordem
    if titulo.referencia_externa:
        yield "referência externa", titulo.referencia_externa
    for evento in titulo.eventos_criacao:
        dados = evento.dados
        if not isinstance(dados, dict):
            continue
        grupo, ordem = dados.get("grupo_manual"), dados.get("parcela")
        if (
            isinstance(grupo, str) and re.fullmatch(r"[0-9a-f]{12}", grupo)
            and _metadados_legados_consistentes(titulo, grupo, ordem, dados.get("total_parcelas"))
            and evento.usuario_id == titulo.criado_por_id
        ):
            yield "grupo legado e ordem da parcela no histórico de criação", grupo, titulo.criado_por_id, ordem
            break


def _metadados_legados_consistentes(titulo, grupo, ordem, total):
    return (
        titulo.origem_detalhe == f"Lançamento manual parcelado {grupo}"
        and type(ordem) is int and type(total) is int and 1 <= ordem <= total
        and titulo.parcela_ordem == ordem and titulo.parcela_total == total
    )


def _parcelas_distintas(a, b):
    if not a.parcela_ordem or not b.parcela_ordem or a.parcela_ordem == b.parcela_ordem:
        return False
    if a.solicitacao_avulsa_id and a.solicitacao_avulsa_id == b.solicitacao_avulsa_id:
        return True
    for chave_a in a.identificadores_auditoria:
        for chave_b in b.identificadores_auditoria:
            if len(chave_a) == len(chave_b) == 4 and chave_a[:-1] == chave_b[:-1]:
                return True
    return False


def _indicios(titulo, outro):
    if _parcelas_distintas(titulo, outro):
        return "semelhante", "Ordens de parcela distintas vinculadas à mesma operação."
    documento = _normalizar(titulo.documento_numero)
    outro_documento = _normalizar(outro.documento_numero)
    if documento and outro_documento and documento != outro_documento:
        return "semelhante", "Números de documento preenchidos e distintos."

    mesmas_parcelas = (titulo.parcela_ordem, titulo.parcela_total) == (outro.parcela_ordem, outro.parcela_total)
    proximo = abs(titulo.criado_em - outro.criado_em) <= JANELA_SUSPEITA
    if titulo.criado_por_id and titulo.criado_por_id == outro.criado_por_id and documento == outro_documento and mesmas_parcelas and proximo:
        motivo = "Mesma obra, beneficiário, valores, vencimento, descrição, origem, responsável e parcela, com documento igual ou ausente e criação em até 10 minutos."
        if titulo.nomes_anexos and titulo.nomes_anexos == outro.nomes_anexos:
            motivo += " Nomes de anexos também coincidem."
        return "forte", motivo
    return "possivel", "Mesma obra, beneficiário, valores, vencimento, descrição e origem."


def _classificar(titulo, tecnicos, semelhantes):
    for identificador in titulo.identificadores_auditoria:
        pares = [outro for outro in tecnicos[identificador] if outro.pk != titulo.pk]
        if pares:
            return "confirmada", f"Mesmo identificador de {identificador[0]}.", pares

    por_classe = defaultdict(list)
    motivos = {}
    for outro in semelhantes[_mesma_obrigacao(titulo)]:
        if outro.pk == titulo.pk:
            continue
        categoria, motivo = _indicios(titulo, outro)
        por_classe[categoria].append(outro)
        motivos.setdefault(categoria, motivo)
    for categoria in ("forte", "possivel", "semelhante"):
        if por_classe[categoria]:
            return categoria, motivos[categoria], por_classe[categoria]
    return None


def linhas_diagnostico_duplicidades():
    titulos = TituloPagar.objects.filter(origem=TituloPagar.Origem.MANUAL).select_related(
        "obra", "fornecedor", "pagamento",
    ).only(
        "numero", "obra__nome", "fornecedor__nome", "fornecedor__nome_fantasia", "fornecedor__codigo",
        "beneficiario_nome", "pagamento__status", "valor_original", "desconto", "juros", "multa",
        "outros_acrescimos", "origem", "origem_detalhe", "criado_em", "criado_por", "status", "vencimento",
        "descricao", "documento_numero", "parcela_ordem", "parcela_total", "referencia_externa",
        "arquivo_documento", "solicitacao_avulsa",
    ).prefetch_related(
        Prefetch("aprovacoes", queryset=AprovacaoTituloFinanceiro.objects.only("titulo", "ciclo", "decisao")),
        Prefetch("anexos", queryset=AnexoTituloPagar.objects.only("titulo", "nome_original")),
        Prefetch("historico", queryset=HistoricoTituloFinanceiro.objects.filter(evento="CRIADO_MANUAL").only(
            "titulo", "dados", "usuario",
        ), to_attr="eventos_criacao"),
    ).order_by("criado_em", "pk")
    tecnicos, semelhantes = defaultdict(list), defaultdict(list)
    for titulo in titulos.iterator(chunk_size=500):
        titulo.identificadores_auditoria = tuple(_identificadores(titulo))
        titulo.nomes_anexos = {_normalizar(anexo.nome_original) for anexo in titulo.anexos.all()} - {""}
        for identificador in titulo.identificadores_auditoria:
            tecnicos[identificador].append(titulo)
        semelhantes[_mesma_obrigacao(titulo)].append(titulo)

    for grupo in semelhantes.values():
        for titulo in grupo:
            resultado = _classificar(titulo, tecnicos, semelhantes)
            if resultado is None:
                continue
            categoria, motivo, relacionados = resultado
            classificacao, recomendacao = CLASSIFICACOES[categoria]
            pagamento = getattr(titulo, "pagamento", None)
            yield (
                titulo.numero, titulo.pk, titulo.obra.nome if titulo.obra_id else "", titulo.beneficiario_exibicao,
                titulo.valor_original, titulo.valor_liquido, titulo.status, titulo.criado_em.isoformat(),
                titulo.vencimento.isoformat() if titulo.vencimento else "", pagamento.status if pagamento else "",
                ", ".join(f"{outro.numero} ({outro.pk})" for outro in relacionados), classificacao, motivo,
                recomendacao, titulo.origem, titulo.criado_por_id, titulo.descricao, titulo.documento_numero,
                titulo.rotulo_parcela, ", ".join(f"{a.ciclo}:{a.decisao}" for a in titulo.aprovacoes.all()),
                len(titulo.anexos.all()) + bool(titulo.arquivo_documento), titulo.referencia_externa,
                titulo.solicitacao_avulsa_id, pagamento.pk if pagamento else None,
            )
