import hashlib

from django.db import models


class ArquivoDrive(models.Model):
    """Relaciona namespace + caminho lógico aos arquivos do Google Drive.

    O caminho completo permanece armazenado; apenas seu hash é indexado para
    respeitar o limite de comprimento de índices no MySQL/utf8mb4.
    """

    namespace = models.CharField(max_length=20)
    caminho = models.CharField(max_length=1024)
    caminho_hash = models.CharField(max_length=64, editable=False)
    drive_id = models.CharField(max_length=256)
    tamanho = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    atualizado_em = models.DateTimeField(auto_now=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['namespace', 'caminho_hash'],
                name='saari_drive_caminho_unico',
            ),
        ]

    def save(self, *args, **kwargs):
        self.caminho_hash = hashlib.sha256(self.caminho.encode('utf-8')).hexdigest()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'caminho_hash'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.namespace}:{self.caminho}'
