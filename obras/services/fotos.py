from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions

MAX_FOTO = 10 * 1024 * 1024
MAX_FOTOS_ENVIO = 12

def validar_fotos(arquivos):
    arquivos = list(arquivos)
    if len(arquivos) > MAX_FOTOS_ENVIO:
        raise ValidationError("Envie no máximo 12 fotos por vez.")
    for arquivo in arquivos:
        if arquivo.size > MAX_FOTO:
            raise ValidationError(f"A foto {arquivo.name} ultrapassa 10 MB.")
        try:
            largura, altura = get_image_dimensions(arquivo)
            if not largura or not altura:
                raise ValueError("Imagem inválida")
            arquivo.seek(0)
        except Exception:
            raise ValidationError(f"O arquivo {arquivo.name} não é uma imagem válida.")
    return arquivos
