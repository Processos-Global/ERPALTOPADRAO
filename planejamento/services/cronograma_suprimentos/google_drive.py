import hashlib
import io
from datetime import datetime

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from planejamento.services.cronograma.google_drive import obter_servico_google_drive


GOOGLE_SHEETS_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleDriveCronogramaSuprimentosError(Exception):
    pass


def _converter_data(data_iso):
    if not data_iso:
        return None
    try:
        return datetime.fromisoformat(str(data_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _hash(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest() if conteudo else ""


def _obter_metadados_arquivo(file_id: str) -> dict:
    servico = obter_servico_google_drive()
    try:
        return (
            servico.files()
            .get(
                fileId=file_id,
                supportsAllDrives=True,
                fields="id,name,mimeType,modifiedTime,size,md5Checksum",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleDriveCronogramaSuprimentosError(
            f"Não foi possível consultar a planilha no Google Drive: {exc}"
        ) from exc


def buscar_planilha_mais_recente(folder_id: str) -> dict:
    if not folder_id:
        raise GoogleDriveCronogramaSuprimentosError(
            "O ID da pasta do cronograma de suprimentos não foi informado."
        )

    servico = obter_servico_google_drive()
    tipos = (
        f"mimeType='{GOOGLE_SHEETS_MIME}' or "
        f"mimeType='{XLSX_MIME}'"
    )

    try:
        resposta = (
            servico.files()
            .list(
                q=f"'{folder_id}' in parents and ({tipos}) and trashed=false",
                orderBy="modifiedTime desc",
                pageSize=1,
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields="files(id,name,mimeType,modifiedTime,size,md5Checksum)",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleDriveCronogramaSuprimentosError(
            f"Não foi possível consultar a pasta do Drive: {exc}"
        ) from exc

    arquivos = resposta.get("files", [])
    if not arquivos:
        raise GoogleDriveCronogramaSuprimentosError(
            "Nenhuma planilha Google ou XLSX foi encontrada na pasta configurada."
        )
    return arquivos[0]


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
            raise GoogleDriveCronogramaSuprimentosError(
                f"Formato de planilha não suportado: {mime_type}"
            )

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, requisicao)
        concluido = False
        while not concluido:
            _, concluido = downloader.next_chunk()

        conteudo = buffer.getvalue()
        if not conteudo:
            raise GoogleDriveCronogramaSuprimentosError(
                "A planilha foi baixada, mas está vazia."
            )
        return conteudo

    except GoogleDriveCronogramaSuprimentosError:
        raise
    except HttpError as exc:
        raise GoogleDriveCronogramaSuprimentosError(
            f"Não foi possível baixar/exportar a planilha: {exc}"
        ) from exc


def obter_dados_planilha(*, file_id: str = "", folder_id: str = "") -> dict:
    if file_id:
        arquivo = _obter_metadados_arquivo(file_id)
    else:
        arquivo = buscar_planilha_mais_recente(folder_id)

    conteudo = baixar_planilha_como_xlsx(
        arquivo["id"],
        arquivo.get("mimeType", ""),
    )

    return {
        "arquivo_drive_id": arquivo.get("id", ""),
        "nome_arquivo": arquivo.get("name", ""),
        "mime_type": arquivo.get("mimeType", ""),
        "data_modificacao_drive": _converter_data(arquivo.get("modifiedTime")),
        "tamanho_arquivo_bytes": len(conteudo),
        "hash_arquivo": _hash(conteudo),
        "hash_google_drive": arquivo.get("md5Checksum", ""),
        "conteudo": conteudo,
    }
