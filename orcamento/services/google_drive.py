import hashlib
import io

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from planejamento.services.cronograma.google_drive import (
    GoogleDriveCronogramaError,
    obter_servico_google_drive,
)


GOOGLE_SHEETS_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleDriveOrcamentoError(Exception):
    """Erro controlado na leitura das planilhas de orçamento no Google Drive."""


def listar_planilhas_pasta(folder_id: str) -> list[dict]:
    """Lista todas as planilhas (Google Sheets ou XLSX) de uma pasta do Drive."""
    if not folder_id:
        raise GoogleDriveOrcamentoError(
            "O ID da pasta de orçamento não foi informado."
        )

    try:
        servico = obter_servico_google_drive()
    except GoogleDriveCronogramaError as exc:
        raise GoogleDriveOrcamentoError(str(exc)) from exc

    tipos = f"mimeType='{GOOGLE_SHEETS_MIME}' or mimeType='{XLSX_MIME}'"

    arquivos = []
    page_token = None

    try:
        while True:
            resposta = (
                servico.files()
                .list(
                    q=(
                        f"'{folder_id}' in parents "
                        f"and ({tipos}) "
                        "and trashed=false"
                    ),
                    orderBy="name",
                    pageSize=200,
                    pageToken=page_token,
                    spaces="drive",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    fields=(
                        "nextPageToken, files("
                        "id,name,mimeType,modifiedTime,size,md5Checksum"
                        ")"
                    ),
                )
                .execute()
            )

            arquivos.extend(resposta.get("files", []))
            page_token = resposta.get("nextPageToken")

            if not page_token:
                break
    except HttpError as exc:
        raise GoogleDriveOrcamentoError(
            f"Não foi possível consultar a pasta do Drive: {exc}"
        ) from exc

    return arquivos


def baixar_planilha_como_xlsx(file_id: str, mime_type: str) -> bytes:
    servico = obter_servico_google_drive()

    try:
        if mime_type == GOOGLE_SHEETS_MIME:
            requisicao = servico.files().export_media(
                fileId=file_id,
                mimeType=XLSX_MIME,
            )
        elif mime_type == XLSX_MIME:
            requisicao = servico.files().get_media(
                fileId=file_id,
                supportsAllDrives=True,
            )
        else:
            raise GoogleDriveOrcamentoError(
                f"Formato de planilha não suportado: {mime_type}"
            )

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, requisicao)

        concluido = False
        while not concluido:
            _, concluido = downloader.next_chunk()

        conteudo = buffer.getvalue()
        if not conteudo:
            raise GoogleDriveOrcamentoError(
                "A planilha foi baixada, mas está vazia."
            )
        return conteudo

    except GoogleDriveOrcamentoError:
        raise
    except HttpError as exc:
        raise GoogleDriveOrcamentoError(
            f"Não foi possível baixar/exportar a planilha: {exc}"
        ) from exc


def calcular_hash_arquivo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest() if conteudo else ""
