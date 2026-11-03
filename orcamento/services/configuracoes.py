from django.conf import settings

from obras.models import Obra


def obter_configuracao_orcamento() -> dict:
    """
    Pasta do Drive com um CSV de orçamento por obra.

    O ID da pasta deve ser informado no .env:
    ORCAMENTO_FOLDER_ID=...
    """
    folder_id = str(getattr(settings, "ORCAMENTO_FOLDER_ID", "")).strip()

    if not folder_id:
        raise ValueError("ORCAMENTO_FOLDER_ID não foi configurado.")

    programa_padrao = str(
        getattr(settings, "ORCAMENTO_PROGRAMA_PADRAO", "") or Obra.Programa.MCMV
    ).strip()

    if programa_padrao not in Obra.Programa.values:
        programa_padrao = Obra.Programa.MCMV

    return {
        "folder_id": folder_id,
        "programa_padrao": programa_padrao,
    }
