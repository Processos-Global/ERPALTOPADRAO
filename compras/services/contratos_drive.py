import io
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings


GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

DEFAULT_FOLDER_ID = "1trjGpEVARl9rX79KBW95gKALfFs1d879"
# ID do arquivo MODELO_CONTRATO_EMPREITADA_VARIAVEIS_SAARI.docx compartilhado.
DEFAULT_TEMPLATE_ID = "1G97QahFyRVQfWpRJwbJTl3dFVdnh8X5C"


def _config():
    base_dir = Path(settings.BASE_DIR)
    return {
        "credentials": Path(getattr(
            settings,
            "GOOGLE_DRIVE_CREDENTIALS_FILE",
            base_dir / "credenciais" / "google-drive.json",
        )),
        "folder_id": getattr(settings, "GOOGLE_DRIVE_CONTRATOS_FOLDER_ID", DEFAULT_FOLDER_ID),
        "template_id": getattr(settings, "GOOGLE_DRIVE_CONTRATO_MODELO_ID", DEFAULT_TEMPLATE_ID),
    }


def _clients():
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Integração Google Drive indisponível. Instale google-api-python-client e google-auth."
        ) from exc

    cfg = _config()
    if not cfg["credentials"].exists():
        raise RuntimeError(f"Arquivo de credenciais não encontrado: {cfg['credentials']}")

    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
    ]
    credentials = Credentials.from_service_account_file(str(cfg["credentials"]), scopes=scopes)
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    docs = build("docs", "v1", credentials=credentials, cache_discovery=False)
    return drive, docs


def _safe_name(value, max_len=90):
    value = re.sub(r"[\\/:*?\"<>|]+", "-", (value or "").strip())
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return (value or "CONTRATO")[:max_len]


def _money(value):
    value = Decimal(value or 0)
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _number_extenso(value):
    try:
        from num2words import num2words
        return num2words(value, lang="pt_BR")
    except Exception:
        return str(value)


def _prazo_extenso(prazo):
    prazo = (prazo or "").strip()
    match = re.match(r"^(\d+)\s*(.*)$", prazo)
    if not match:
        return prazo
    numero = int(match.group(1))
    unidade = match.group(2).strip()
    extenso = _number_extenso(numero)
    return f"{extenso} {unidade}".strip()


def _money_extenso(value):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    inteiro = int(value)
    centavos = int((value - inteiro) * 100)
    texto = _number_extenso(inteiro)
    texto += " real" if inteiro == 1 else " reais"
    if centavos:
        texto += " e " + _number_extenso(centavos)
        texto += " centavo" if centavos == 1 else " centavos"
    return texto


def _date_extenso(value):
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{value.day:02d} de {meses[value.month - 1]} de {value.year}"


def _area_extenso(value):
    if value is None:
        return ""
    inteiro = int(Decimal(value))
    return _number_extenso(inteiro)


def _qualificacao_avalistas(contrato):
    partes = []
    if contrato.avalista_1_nome:
        partes.append(f"O(a) Sr.(a) {contrato.avalista_1_nome}, CPF {contrato.avalista_1_cpf or 'não informado'}, também será avalista do presente contrato.")
    if contrato.avalista_2_nome:
        partes.append(f"O(a) Sr.(a) {contrato.avalista_2_nome}, CPF {contrato.avalista_2_cpf or 'não informado'}, também será avalista do presente contrato.")
    return " ".join(partes)


def placeholders_contrato(contrato):
    obra_nome = getattr(contrato.obra, "nome", None) or getattr(contrato.obra, "codigo", None) or str(contrato.obra)
    obra_endereco = (
        getattr(contrato.obra, "endereco", None)
        or getattr(contrato.obra, "endereco_obra", None)
        or obra_nome
    )
    prazo = (contrato.prazo_execucao or "").strip()
    return {
        "{{obra_nome}}": obra_nome,
        "{{obra_endereco}}": obra_endereco,
        "{{contratado_razao_social}}": contrato.contratado_razao_social,
        "{{contratado_cnpj}}": contrato.contratado_cnpj,
        "{{contratado_endereco}}": contrato.contratado_endereco,
        "{{contratado_email}}": contrato.contratado_email,
        "{{representante_nome}}": contrato.representante_nome,
        "{{representante_nacionalidade}}": contrato.representante_nacionalidade,
        "{{representante_estado_civil}}": contrato.representante_estado_civil,
        "{{representante_profissao}}": contrato.representante_profissao,
        "{{representante_cpf}}": contrato.representante_cpf,
        "{{representante_endereco}}": contrato.representante_endereco,
        "{{modalidade_fornecimento}}": contrato.modalidade_fornecimento,
        "{{objeto_contrato}}": contrato.objeto_contrato,
        "{{area_obra}}": "" if contrato.area_obra is None else f"{contrato.area_obra:.2f}".replace(".", ","),
        "{{area_obra_extenso}}": _area_extenso(contrato.area_obra),
        "{{descricao_ambientes_objeto}}": contrato.descricao_ambientes_objeto,
        "{{escritorio_arquitetura}}": contrato.escritorio_arquitetura,
        "{{responsavel_supervisao}}": contrato.responsavel_supervisao,
        "{{prazo_execucao}}": prazo,
        "{{prazo_execucao_extenso}}": _prazo_extenso(prazo),
        "{{multa_atraso_formatada}}": _money(contrato.multa_atraso),
        "{{multa_atraso_extenso}}": _money_extenso(contrato.multa_atraso),
        "{{valor_total_formatado}}": _money(contrato.valor_total),
        "{{valor_total_extenso}}": _money_extenso(contrato.valor_total),
        "{{favorecido_nome}}": contrato.favorecido_nome,
        "{{favorecido_documento_tipo}}": contrato.favorecido_documento_tipo,
        "{{favorecido_documento}}": contrato.favorecido_documento,
        "{{banco}}": contrato.banco,
        "{{agencia}}": contrato.agencia,
        "{{conta}}": contrato.conta,
        "{{operacao}}": contrato.operacao,
        "{{pix}}": contrato.pix,
        "{{qualificacao_avalistas_adicionais}}": _qualificacao_avalistas(contrato),
        "{{avalista_1_nome}}": contrato.avalista_1_nome,
        "{{avalista_1_cpf}}": contrato.avalista_1_cpf,
        "{{avalista_2_nome}}": contrato.avalista_2_nome,
        "{{avalista_2_cpf}}": contrato.avalista_2_cpf,
        "{{cidade_assinatura}}": contrato.cidade_assinatura,
        "{{data_contrato_extenso}}": _date_extenso(contrato.data_contrato),
        "{{anexo_1_preenchimento_manual}}": "[PREENCHIMENTO MANUAL DO CRONOGRAMA FÍSICO-FINANCEIRO]",
    }


def _arquivo_metadata(drive, file_id):
    return drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,parents,webViewLink,modifiedTime,md5Checksum,appProperties,driveId",
        supportsAllDrives=True,
    ).execute()


def _garantir_modelo_google_docs(drive):
    from googleapiclient.http import MediaIoBaseUpload

    cfg = _config()
    meta = _arquivo_metadata(drive, cfg["template_id"])
    if meta.get("mimeType") == GOOGLE_DOC_MIME:
        return meta["id"]

    marker_name = f"MODELO_INTERNO_GOOGLE_DOCS__{cfg['template_id']}"
    escaped_name = marker_name.replace("'", "\\'")
    q = f"name = '{escaped_name}' and '{cfg['folder_id']}' in parents and trashed = false"
    found = drive.files().list(
        q=q,
        fields="files(id,name,mimeType,appProperties)",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    source_version = meta.get("modifiedTime") or meta.get("md5Checksum") or "unknown"
    for item in found:
        props = item.get("appProperties") or {}
        if props.get("saari_source_version") == source_version:
            return item["id"]
        try:
            drive.files().update(
                fileId=item["id"],
                body={"trashed": True},
                supportsAllDrives=True,
            ).execute()
        except Exception:
            pass

    req = drive.files().get_media(
        fileId=cfg["template_id"],
        supportsAllDrives=True,
    )
    data = io.BytesIO(req.execute())
    data.seek(0)
    media = MediaIoBaseUpload(data, mimetype=meta.get("mimeType") or DOCX_MIME, resumable=False)
    created = drive.files().create(
        body={
            "name": marker_name,
            "mimeType": GOOGLE_DOC_MIME,
            "parents": [cfg["folder_id"]],
            "appProperties": {"saari_source_version": source_version},
        },
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def garantir_pasta_contrato(contrato):
    drive, _ = _clients()
    if contrato.drive_folder_id:
        try:
            _arquivo_metadata(drive, contrato.drive_folder_id)
            return contrato.drive_folder_id
        except Exception:
            pass

    cfg = _config()
    nome = _safe_name(f"{contrato.numero} - {contrato.obra} - {contrato.contratado_razao_social}")
    folder = drive.files().create(
        body={"name": nome, "mimeType": GOOGLE_FOLDER_MIME, "parents": [cfg["folder_id"]]},
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()
    contrato.drive_folder_id = folder["id"]
    contrato.save(update_fields=["drive_folder_id", "atualizado_em"])
    return folder["id"]


def gerar_previa_google_doc(contrato):
    drive, docs = _clients()
    template_id = _garantir_modelo_google_docs(drive)
    folder_id = garantir_pasta_contrato(contrato)

    if contrato.google_doc_id:
        try:
            drive.files().update(
                fileId=contrato.google_doc_id,
                body={"trashed": True},
                supportsAllDrives=True,
            ).execute()
        except Exception:
            pass

    nome = _safe_name(f"{contrato.numero} - {contrato.contratado_razao_social} - PREVIA")
    copied = drive.files().copy(
        fileId=template_id,
        body={"name": nome, "parents": [folder_id]},
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()

    requests = []
    for marcador, valor in placeholders_contrato(contrato).items():
        requests.append({
            "replaceAllText": {
                "containsText": {"text": marcador, "matchCase": True},
                "replaceText": str(valor or ""),
            }
        })
    if requests:
        docs.documents().batchUpdate(documentId=copied["id"], body={"requests": requests}).execute()

    meta = _arquivo_metadata(drive, copied["id"])
    contrato.google_doc_id = copied["id"]
    contrato.google_doc_url = meta.get("webViewLink", "")
    contrato.save(update_fields=["google_doc_id", "google_doc_url", "atualizado_em"])
    return contrato.google_doc_url


def finalizar_google_doc(contrato):
    drive, _ = _clients()
    if not contrato.google_doc_id:
        gerar_previa_google_doc(contrato)
    nome = _safe_name(f"{contrato.numero} - {contrato.contratado_razao_social}")
    drive.files().update(
        fileId=contrato.google_doc_id,
        body={"name": nome},
        supportsAllDrives=True,
    ).execute()
    meta = _arquivo_metadata(drive, contrato.google_doc_id)
    contrato.google_doc_url = meta.get("webViewLink", "")
    contrato.save(update_fields=["google_doc_url", "atualizado_em"])
    return contrato.google_doc_url


def exportar_docx_bytes(contrato):
    drive, _ = _clients()
    if not contrato.google_doc_id:
        raise RuntimeError("Contrato ainda não possui Google Doc gerado.")
    return drive.files().export(fileId=contrato.google_doc_id, mimeType=DOCX_MIME).execute()


def upload_contrato_assinado(contrato):
    from googleapiclient.http import MediaIoBaseUpload

    if not contrato.arquivo_assinado:
        raise RuntimeError("Contrato assinado não anexado.")
    drive, _ = _clients()
    folder_id = garantir_pasta_contrato(contrato)
    import mimetypes
    arquivo = contrato.arquivo_assinado
    mimetype = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
    arquivo.open("rb")
    try:
        data = io.BytesIO(arquivo.read())
    finally:
        arquivo.close()
    data.seek(0)
    media = MediaIoBaseUpload(data, mimetype=mimetype, resumable=False)
    created = drive.files().create(
        body={
            "name": _safe_name(f"{contrato.numero} - CONTRATO ASSINADO") + Path(arquivo.name).suffix,
            "parents": [folder_id],
        },
        media_body=media,
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()
    contrato.drive_assinado_id = created["id"]
    contrato.drive_assinado_url = created.get("webViewLink", "")
    contrato.save(update_fields=["drive_assinado_id", "drive_assinado_url", "atualizado_em"])
    return contrato.drive_assinado_url
