from django.db import migrations

ACOES = {'OBRAS': ['visualizar', 'editar_dados', 'gerenciar_ficha_tecnica', 'criar_fvs', 'editar_fvs', 'aprovar_fvs'], 'ALMOXARIFADO': ['visualizar', 'entrada', 'saida', 'transferencia', 'depreciacao', 'ajuste'], 'DIARIO_OBRA': ['visualizar', 'criar', 'editar'], 'VISTORIAS': ['visualizar', 'pre_habite_se', 'pos_habite_se']}

def migrar(apps, schema_editor):
    PermissaoModulo = apps.get_model('usuarios', 'PermissaoModulo')
    PermissaoAcao = apps.get_model('usuarios', 'PermissaoAcao')
    for registro in PermissaoModulo.objects.filter(modulo='OBRAS', ativo=True).iterator():
        for modulo, acoes in ACOES.items():
            for acao in acoes:
                permitir = acao == 'visualizar' or registro.nivel in ('EDICAO', 'APROVACAO', 'ADMINISTRADOR')
                if acao == 'aprovar_fvs':
                    permitir = registro.nivel in ('APROVACAO', 'ADMINISTRADOR')
                PermissaoAcao.objects.get_or_create(usuario_id=registro.usuario_id, modulo=modulo, acao=acao, defaults={'permitido': permitir})

class Migration(migrations.Migration):
    dependencies = [('usuarios', '0010_permissoes_acoes')]
    operations = [migrations.RunPython(migrar, migrations.RunPython.noop)]
