def celula_csv(valor):
    if isinstance(valor, str) and (
        valor.startswith(("\t", "\r", "\n")) or valor.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + valor
    return valor
