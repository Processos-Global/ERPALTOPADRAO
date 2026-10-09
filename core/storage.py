"""Storage híbrido SAARI. Mantém FileField e caminhos lógicos legados."""
import os
from pathlib import Path
from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


class _SaariHybridMixin:
    namespace = 'public'

    def _existe_local(self, name):
        # Evita FileSystemStorage.exists() -> self.path() -> exists() recursivo.
        return os.path.lexists(FileSystemStorage.path(self, name))

    def _registro(self, name):
        if not getattr(settings, 'SAARI_DRIVE_ENABLED', False):
            return None
        from core.models import ArquivoDrive
        return ArquivoDrive.objects.filter(namespace=self.namespace, caminho=name).first()

    def _open(self, name, mode='rb'):
        if self._existe_local(name):
            return super()._open(name, mode)
        if mode not in ('rb', 'r'):
            raise ValueError('Arquivos remotos são somente leitura')
        registro = self._registro(name)
        if registro is None:
            raise FileNotFoundError(name)
        from core.services.arquivos_drive import baixar_para
        # SpooledTemporaryFile evita manter anexos grandes integralmente em RAM.
        from tempfile import SpooledTemporaryFile
        temp = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
        try:
            baixar_para(registro.drive_id, temp)
            temp.seek(0)
            return File(temp, name=Path(name).name)
        except Exception:
            temp.close()
            raise

    def exists(self, name):
        return self._existe_local(name) or self._registro(name) is not None

    def size(self, name):
        if self._existe_local(name):
            return super().size(name)
        registro = self._registro(name)
        if registro:
            return registro.tamanho
        raise FileNotFoundError(name)

    def delete(self, name):
        # Exclui somente arquivo local; remoto retido para impedir perda acidental.
        # Uma política posterior deverá administrar exclusão remota e retenção.
        if self._existe_local(name):
            return super().delete(name)
        return None

    def path(self, name):
        if not self._existe_local(name) and self._registro(name):
            raise NotImplementedError('Arquivo remoto não possui caminho no disco; use .open()')
        return super().path(name)


@deconstructible
class SaariPublicStorage(_SaariHybridMixin, FileSystemStorage):
    namespace = 'public'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.MEDIA_ROOT)
        kwargs.setdefault('base_url', settings.MEDIA_URL)
        super().__init__(*args, **kwargs)

    def url(self, name):
        if getattr(settings, 'SAARI_DRIVE_ENABLED', False) and getattr(settings, 'SAARI_DRIVE_SERVE_REMOTE', False):
            return reverse('core:arquivo_publico', kwargs={'caminho': name})
        return super().url(name)


@deconstructible
class PrivateMediaStorage(_SaariHybridMixin, FileSystemStorage):
    namespace = 'private'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.PRIVATE_MEDIA_ROOT)
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)


private_media_storage = PrivateMediaStorage()
