"""Diagnóstico somente leitura; não imprime senhas nem modifica registros."""
from collections import defaultdict
from django.core.management.base import BaseCommand
from cadastros.models import Cliente
from usuarios.services.clientes import normalizar_documento


class Command(BaseCommand):
    help='Lista IDs de clientes com associações incompletas ou documentos repetidos. Não altera dados.'

    def handle(self, *args, **options):
        documentos=defaultdict(list)
        total=0
        for c in Cliente.objects.select_related('usuario').prefetch_related('vinculos').iterator(chunk_size=500):
            total+=1
            if not c.usuario_id:self.stdout.write(f'Cliente #{c.pk}: sem usuário; requer associação explícita em Usuários.')
            if c.portal_habilitado and not any(v.ativo for v in c.vinculos.all()):self.stdout.write(f'Cliente #{c.pk}: portal habilitado sem vínculo ativo.')
            if c.usuario_id and (c.usuario.is_staff or c.usuario.is_superuser or c.usuario.permissoes_modulos_erp.filter(ativo=True).exists()):self.stdout.write(f'Cliente #{c.pk}: conta com privilégios internos; revisar.')
            doc=normalizar_documento(c.documento)
            if doc:documentos[doc].append(c.pk)
        for ids in documentos.values():
            if len(ids)>1:self.stdout.write('Documento repetido entre clientes: '+', '.join(map(str,ids))+'. Revisão manual necessária.')
        self.stdout.write(f'{total} clientes analisados. Nenhuma alteração realizada.')
