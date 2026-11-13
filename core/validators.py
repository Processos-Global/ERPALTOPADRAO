from __future__ import annotations

from pathlib import Path

from django.core.exceptions import ValidationError


DOCUMENT_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx", ".xml"
}
DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/xml",
    "text/xml",
    "application/octet-stream",  # alguns navegadores enviam Office/PDF assim
}
DEFAULT_MAX_UPLOAD_MB = 20


def validar_documento_upload(arquivo, *, max_mb: int = DEFAULT_MAX_UPLOAD_MB):
    """Valida anexos de negócio antes de persistir no armazenamento."""
    if not arquivo:
        return arquivo

    extensao = Path(arquivo.name or "").suffix.lower()
    if extensao not in DOCUMENT_EXTENSIONS:
        permitidas = ", ".join(sorted(DOCUMENT_EXTENSIONS))
        raise ValidationError(
            f"Tipo de arquivo não permitido. Extensões aceitas: {permitidas}."
        )

    limite = max_mb * 1024 * 1024
    if getattr(arquivo, "size", 0) > limite:
        raise ValidationError(f"O arquivo excede o limite de {max_mb} MB.")

    content_type = (getattr(arquivo, "content_type", "") or "").lower().strip()
    if content_type and content_type not in DOCUMENT_MIME_TYPES:
        raise ValidationError("O tipo de conteúdo do arquivo não é permitido.")

    return arquivo
