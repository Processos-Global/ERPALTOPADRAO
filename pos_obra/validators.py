from pathlib import Path
from django.core.exceptions import ValidationError

MAX_ANEXO_BYTES = 15 * 1024 * 1024
EXTENSOES = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.doc', '.docx'}

def validar_anexo(arquivo):
    if arquivo.size > MAX_ANEXO_BYTES:
        raise ValidationError('O arquivo deve ter até 15 MB.')
    extensao = Path(arquivo.name).suffix.lower()
    if extensao not in EXTENSOES:
        raise ValidationError('Envie PDF, imagem (JPG, PNG, WEBP, GIF) ou documento Word.')
    inicio = arquivo.read(16)
    arquivo.seek(0)
    assinaturas = {
        '.pdf': inicio.startswith(b'%PDF-'),
        '.jpg': inicio.startswith(b'\xff\xd8\xff'),
        '.jpeg': inicio.startswith(b'\xff\xd8\xff'),
        '.png': inicio.startswith(b'\x89PNG\r\n\x1a\n'),
        '.gif': inicio.startswith((b'GIF87a', b'GIF89a')),
        '.webp': inicio.startswith(b'RIFF') and inicio[8:12] == b'WEBP',
        '.doc': inicio.startswith(bytes.fromhex('D0CF11E0A1B11AE1')),
        '.docx': inicio.startswith(b'PK\x03\x04'),
    }
    if not assinaturas[extensao]:
        raise ValidationError('O conteúdo do arquivo não corresponde ao formato informado.')
