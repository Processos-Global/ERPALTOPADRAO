"""Cliente Drive para cópia segura de mídias, isolado da integração de contratos."""
from functools import lru_cache
from pathlib import Path
from django.conf import settings

MIME_FOLDER = 'application/vnd.google-apps.folder'


@lru_cache(maxsize=1)
def cliente():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    cred = Path(settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE)
    if not cred.is_absolute():
        cred = Path(settings.BASE_DIR) / cred
    credentials = Credentials.from_service_account_file(str(cred), scopes=['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=credentials, cache_discovery=False)


def _q(value):
    return value.replace(chr(92), chr(92) * 2).replace(chr(39), chr(92) + chr(39))


def obter_pasta(pai, nome):
    drive = cliente()
    encontrados = drive.files().list(
        q=f"'{_q(pai)}' in parents and name = '{_q(nome)}' and mimeType = '{MIME_FOLDER}' and trashed = false",
        fields='nextPageToken,files(id,name)', pageSize=100,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get('files', [])
    if encontrados:
        return encontrados[0]['id']
    criado = drive.files().create(body={'name': nome, 'parents': [pai], 'mimeType': MIME_FOLDER}, fields='id', supportsAllDrives=True).execute()
    return criado['id']


def pasta_caminho(namespace, caminho):
    atual = settings.SAARI_ARQUIVOS_DRIVE_FOLDER_ID
    if not atual:
        raise RuntimeError('SAARI_ARQUIVOS_DRIVE_FOLDER_ID não configurado')
    for segmento in [namespace, *Path(caminho).parts[:-1]]:
        atual = obter_pasta(atual, segmento)
    return atual


def enviar(namespace, caminho, stream, mime, sha256):
    from googleapiclient.http import MediaIoBaseUpload
    pasta = pasta_caminho(namespace, caminho)
    stream.seek(0)
    # appProperties auxilia na recuperação de uploads após falha de gravação no DB.
    props = {'saari_namespace': namespace, 'saari_sha256': sha256, 'saari_path': caminho[:124]}
    drive = cliente()
    existing = drive.files().list(q=f"'{_q(pasta)}' in parents and name = '{_q(Path(caminho).name)}' and trashed = false", fields='files(id,appProperties,size)', pageSize=100, supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    for item in existing:
        if (item.get('appProperties') or {}).get('saari_sha256') == sha256:
            return item['id']
    result = drive.files().create(
        body={'name': Path(caminho).name, 'parents': [pasta], 'appProperties': props},
        media_body=MediaIoBaseUpload(stream, mimetype=mime, resumable=True),
        fields='id', supportsAllDrives=True,
    ).execute()
    return result['id']


def baixar_para(drive_id, destino):
    from googleapiclient.http import MediaIoBaseDownload
    request = cliente().files().get_media(fileId=drive_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(destino, request)
    terminado = False
    while not terminado:
        _, terminado = downloader.next_chunk()


def metadados(drive_id):
    return cliente().files().get(fileId=drive_id, fields='id,size,trashed', supportsAllDrives=True).execute()
