import unicodedata


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.upper().strip().split())


def chave_estavel_item(obra_id, item, local):
    return int(obra_id), _normalizar(item), _normalizar(local)
