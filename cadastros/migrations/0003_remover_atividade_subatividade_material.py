from django.db import migrations, models
from django.db.models import Count


def validar_catalogo_simplificado(apps, schema_editor):
    """
    Antes de remover Atividade/Subatividade, garante que o catálogo
    continuará único considerando apenas:

        nome + especificacao + unidade

    Caso existam duplicidades, a migration é interrompida para evitar
    perda ou associação incorreta de materiais.
    """
    Material = apps.get_model("cadastros", "Material")

    duplicados = (
        Material.objects
        .values(
            "nome",
            "especificacao",
            "unidade_id",
        )
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by(
            "nome",
            "especificacao",
            "unidade_id",
        )
    )

    primeiro = duplicados.first()

    if primeiro:
        raise RuntimeError(
            "Não foi possível simplificar o catálogo de materiais porque existem "
            "materiais duplicados com o mesmo nome, especificação e unidade. "
            f"Primeiro conflito: {primeiro}. "
            "Corrija os duplicados e rode a migration novamente."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0002_alter_fornecedor_avaliacao"),
    ]

    operations = [

        # ---------------------------------------------------------
        # A constraint antiga existe no STATE do Django,
        # mas já não existe fisicamente no MySQL.
        # ---------------------------------------------------------
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="material",
                    name="cad_material_catalogo_uniq",
                ),
            ],
            database_operations=[],
        ),

        # ---------------------------------------------------------
        # Validação antes da simplificação definitiva do catálogo.
        # ---------------------------------------------------------
        migrations.RunPython(
            validar_catalogo_simplificado,
            migrations.RunPython.noop,
        ),

        # ---------------------------------------------------------
        # Índice antigo.
        #
        # Já não existe fisicamente no MySQL.
        # Remove apenas do STATE do Django.
        # ---------------------------------------------------------
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="material",
                    name="cad_mat_ativ_sub_idx",
                ),
            ],
            database_operations=[],
        ),

        # ---------------------------------------------------------
        # Campo subatividade.
        #
        # A coluna subatividade_id já não existe fisicamente
        # no MySQL.
        # ---------------------------------------------------------
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="material",
                    name="subatividade",
                ),
            ],
            database_operations=[],
        ),

        # ---------------------------------------------------------
        # Campo atividade.
        #
        # A coluna atividade_id já não existe fisicamente
        # no MySQL.
        # ---------------------------------------------------------
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="material",
                    name="atividade",
                ),
            ],
            database_operations=[],
        ),

        # ---------------------------------------------------------
        # Modelo SubatividadeMaterial.
        #
        # A tabela cadastros_subatividadematerial já foi removida
        # fisicamente do MySQL.
        #
        # Portanto apagamos apenas do STATE do Django.
        # ---------------------------------------------------------
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="SubatividadeMaterial",
                ),
            ],
            database_operations=[],
        ),

        # ---------------------------------------------------------
        # Modelo AtividadeMaterial.
        #
        # Como o banco já sofreu a remoção parcial dessa estrutura,
        # tratamos também apenas no STATE para evitar outro
        # "Unknown table".
        # ---------------------------------------------------------
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="AtividadeMaterial",
                ),
            ],
            database_operations=[],
        ),

        # ---------------------------------------------------------
        # Nova ordenação do catálogo simplificado.
        # AlterModelOptions altera apenas o estado do Django.
        # ---------------------------------------------------------
        migrations.AlterModelOptions(
            name="material",
            options={
                "ordering": (
                    "nome",
                    "especificacao",
                    "codigo",
                ),
                "verbose_name": "Material",
                "verbose_name_plural": "Materiais",
            },
        ),

        # ---------------------------------------------------------
        # Nova constraint de unicidade:
        #
        # nome + especificacao + unidade
        #
        # Essa operação ainda deve ser aplicada fisicamente no banco.
        # ---------------------------------------------------------
        migrations.AddConstraint(
            model_name="material",
            constraint=models.UniqueConstraint(
                fields=(
                    "nome",
                    "especificacao",
                    "unidade",
                ),
                name="cad_material_catalogo_uniq",
            ),
        ),
    ]