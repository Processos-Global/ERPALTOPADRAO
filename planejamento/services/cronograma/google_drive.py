import hashlib
import io
import os
from datetime import datetime

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload


GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleDriveCronogramaError(Exception):
    """Erro controlado na leitura do cronograma no Google Drive."""


def _obter_caminho_credencial() -> str:
    caminho_configurado = str(
        getattr(settings, "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "")
        or os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "")
    ).strip()

    if not caminho_configurado:
        raise GoogleDriveCronogramaError(
            "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE não foi configurado."
        )

    if os.path.isabs(caminho_configurado):
        caminho = caminho_configurado
    else:
        caminho = settings.BASE_DIR / caminho_configurado

    if not os.path.exists(caminho):
        raise GoogleDriveCronogramaError(
            f"Credencial do Google Drive não encontrada em: {caminho}"
        )

    return str(caminho)


def obter_servico_google_drive():
    try:
        credenciais = service_account.Credentials.from_service_account_file(
            _obter_caminho_credencial(),
            scopes=GOOGLE_DRIVE_SCOPES,
        )
        return build(
            "drive",
            "v3",
            credentials=credenciais,
            cache_discovery=False,
        )
    except GoogleDriveCronogramaError:
        raise
    except Exception as exc:
        raise GoogleDriveCronogramaError(
            f"Não foi possível autenticar no Google Drive: {exc}"
        ) from exc


def buscar_csv_mais_recente(folder_id: str) -> dict:
    if not folder_id:
        raise GoogleDriveCronogramaError(
            "O ID da pasta do cronograma não foi informado."
        )

    servico = obter_servico_google_drive()

    try:
        resposta = (
            servico.files()
            .list(
                q=(
                    f"'{folder_id}' in parents "
                    "and mimeType='text/csv' "
                    "and trashed=false"
                ),
                orderBy="modifiedTime desc",
                pageSize=1,
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields=(
                    "files("
                    "id,name,mimeType,modifiedTime,size,md5Checksum"
                    ")"
                ),
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleDriveCronogramaError(
            f"Não foi possível consultar a pasta do Drive: {exc}"
        ) from exc

    arquivos = resposta.get("files", [])
    if not arquivos:
        raise GoogleDriveCronogramaError(
            "Nenhum arquivo CSV foi encontrado na pasta configurada."
        )

    return arquivos[0]


def baixar_arquivo_drive(file_id: str) -> bytes:
    if not file_id:
        raise GoogleDriveCronogramaError(
            "O ID do arquivo do Google Drive não foi informado."
        )

    servico = obter_servico_google_drive()

    try:
        requisicao = servico.files().get_media(
            fileId=file_id,
            supportsAllDrives=True,
        )
        arquivo_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(arquivo_buffer, requisicao)

        concluido = False
        while not concluido:
            _, concluido = downloader.next_chunk()

        return arquivo_buffer.getvalue()
    except HttpError as exc:
        raise GoogleDriveCronogramaError(
            f"Não foi possível baixar o CSV do Google Drive: {exc}"
        ) from exc


def calcular_hash_arquivo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest() if conteudo else ""


def converter_data_google_drive(data_iso):
    if not data_iso:
        return None
    try:
        return datetime.fromisoformat(str(data_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def obter_dados_csv_mais_recente(folder_id: str) -> dict:
    arquivo = buscar_csv_mais_recente(folder_id)
    conteudo = baixar_arquivo_drive(arquivo["id"])

    if not conteudo:
        raise GoogleDriveCronogramaError(
            "O CSV mais recente foi baixado, mas está vazio."
        )

    return {
        "arquivo_drive_id": arquivo.get("id", ""),
        "nome_arquivo": arquivo.get("name", ""),
        "mime_type": arquivo.get("mimeType", ""),
        "data_modificacao_drive": converter_data_google_drive(
            arquivo.get("modifiedTime")
        ),
        "tamanho_arquivo_bytes": len(conteudo),
        "hash_arquivo": calcular_hash_arquivo(conteudo),
        "hash_google_drive": arquivo.get("md5Checksum", ""),
        "conteudo": conteudo,
    }
