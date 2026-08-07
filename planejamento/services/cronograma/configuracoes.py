from django.conf import settings


def obter_configuracao_cronograma() -> dict:
    """
    Configuração exclusiva do cronograma de obras Alto Padrão.

    O ID da pasta deve ser informado no .env:
    CRONOGRAMA_ALTO_PADRAO_FOLDER_ID=...
    """
    folder_id = str(
        getattr(settings, "CRONOGRAMA_ALTO_PADRAO_FOLDER_ID", "")
    ).strip()

    if not folder_id:
        raise ValueError(
            "CRONOGRAMA_ALTO_PADRAO_FOLDER_ID não foi configurado."
        )

    return {
        "nome": "Alto Padrão",
        "folder_id": folder_id,
        "separador": ";",
        "dayfirst": True,
    }
