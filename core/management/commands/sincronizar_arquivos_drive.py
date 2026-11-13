import hashlib
import mimetypes
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.models import ArquivoDrive
from core.services.arquivos_drive import enviar, metadados, baixar_para
from tempfile import SpooledTemporaryFile


class Command(BaseCommand):
    help = 'Envia cópias de media e private_media ao Drive. Não remove arquivos locais.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='Efetua upload (padrão: simulação)')
        parser.add_argument('--limit', type=int, default=0, help='Limita número de arquivos')
        parser.add_argument('--namespace', choices=('public', 'private', 'all'), default='all')

    def handle(self, *args, **opts):
        if not settings.SAARI_DRIVE_ENABLED:
            raise CommandError('Habilite SAARI_DRIVE_ENABLED=True para executar a sincronização')
        if not settings.SAARI_ARQUIVOS_DRIVE_FOLDER_ID:
            raise CommandError('Pasta do Drive não configurada')
        total = enviados = pulados = falhas = 0
        roots = {'public': Path(settings.MEDIA_ROOT), 'private': Path(settings.PRIVATE_MEDIA_ROOT)}
        for namespace, root in roots.items():
            if opts['namespace'] not in ('all', namespace) or not root.is_dir():
                continue
            for path in sorted(root.rglob('*')):
                if not path.is_file() or path.is_symlink():
                    continue
                if opts['limit'] and total >= opts['limit']:
                    break
                total += 1
                relativo = path.relative_to(root).as_posix()
                try:
                    size_before = path.stat().st_size
                    checksum = hashlib.sha256()
                    with path.open('rb') as inp:
                        for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                            checksum.update(chunk)
                    digest = checksum.hexdigest()
                    existing = ArquivoDrive.objects.filter(namespace=namespace, caminho=relativo).first()
                    if existing and existing.tamanho == size_before and existing.sha256 == digest:
                        # Na simulação não faz chamadas ao Google Drive.
                        if opts['execute']:
                            meta = metadados(existing.drive_id)
                            if not meta.get('trashed') and int(meta.get('size', -1)) == size_before:
                                pulados += 1
                                continue
                        else:
                            pulados += 1
                            continue
                    if not opts['execute']:
                        self.stdout.write(f'SIMULAR {namespace}/{relativo} ({size_before} bytes)')
                        continue
                    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                    with path.open('rb') as arquivo:
                        drive_id = enviar(namespace, relativo, arquivo, mime, digest)
                    meta = metadados(drive_id)
                    if meta.get('trashed') or int(meta.get('size', -1)) != size_before:
                        raise RuntimeError('Verificação do tamanho remoto falhou')
                    with SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b') as temporario:
                        baixar_para(drive_id, temporario)
                        temporario.seek(0)
                        remoto_hash = hashlib.sha256()
                        for bloco in iter(lambda: temporario.read(1024 * 1024), b''):
                            remoto_hash.update(bloco)
                    if remoto_hash.hexdigest() != digest:
                        raise RuntimeError('Hash SHA-256 remoto divergente')
                    # Revalida o conteúdo local após upload para evitar registrar
                    # uma versão antiga caso o arquivo tenha sido sobrescrito.
                    checksum_final = hashlib.sha256()
                    with path.open('rb') as novamente:
                        for bloco in iter(lambda: novamente.read(1024 * 1024), b''):
                            checksum_final.update(bloco)
                    if path.stat().st_size != size_before or checksum_final.hexdigest() != digest:
                        raise RuntimeError('Arquivo local alterado durante upload; vínculo não registrado')
                    ArquivoDrive.objects.update_or_create(namespace=namespace, caminho=relativo, defaults={'drive_id': drive_id, 'tamanho': size_before, 'sha256': digest})
                    enviados += 1
                    self.stdout.write(self.style.SUCCESS(f'ENVIADO {namespace}/{relativo}'))
                except Exception as exc:
                    falhas += 1
                    self.stderr.write(f'FALHA {namespace}/{relativo}: {exc}')
            if opts['limit'] and total >= opts['limit']:
                break
        self.stdout.write(f'Total: {total} | enviados: {enviados} | existentes: {pulados} | falhas: {falhas} | modo: {"UPLOAD" if opts["execute"] else "SIMULAÇÃO"}')
        if falhas:
            raise CommandError(f'{falhas} arquivo(s) falharam; nenhum arquivo local foi removido')
