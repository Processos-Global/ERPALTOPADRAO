from django.conf import settings


def obter_configuracao_cronograma_suprimentos() -> dict:
    file_id = str(
        getattr(settings, "CRONOGRAMA_SUPRIMENTOS_FILE_ID", "") or ""
    ).strip()
    folder_id = str(
        getattr(settings, "CRONOGRAMA_SUPRIMENTOS_FOLDER_ID", "") or ""
    ).strip()

    if not file_id and not folder_id:
        raise ValueError(
            "Configure CRONOGRAMA_SUPRIMENTOS_FILE_ID ou "
            "CRONOGRAMA_SUPRIMENTOS_FOLDER_ID no .env/settings."
        )

    return {
        "nome": "Cronograma de Suprimentos Alto Padrão",
        "file_id": file_id,
        "folder_id": folder_id,
        "ignorar_prefixos_abas": ("PLAN","COPIA DE",),
        # Projeto antigo que não deve entrar no ERP.
        "ignorar_abas": ("11-07-21",),
    }
