from financeiro.models import HistoricoTituloFinanceiro


def registrar_evento(titulo, evento, descricao, usuario=None, dados=None):
    return HistoricoTituloFinanceiro.objects.create(
        titulo=titulo,
        evento=evento,
        descricao=descricao,
        usuario=usuario,
        dados=dados or {},
    )
