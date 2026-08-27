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

        # Remove fisicamente e do state a constraint antiga
        migrations.RemoveConstraint(
            model_name="material",
            name="cad_material_catalogo_uniq",
        ),

        # Confere se o novo catálogo poderá ser único
        migrations.RunPython(
            validar_catalogo_simplificado,
            migrations.RunPython.noop,
        ),

        # Remove o índice antigo
        migrations.RemoveIndex(
            model_name="material",
            name="cad_mat_ativ_sub_idx",
        ),

        # Remove os vínculos antigos do Material
        migrations.RemoveField(
            model_name="material",
            name="subatividade",
        ),

        migrations.RemoveField(
            model_name="material",
            name="atividade",
        ),

        # Remove os modelos antigos
        migrations.DeleteModel(
            name="SubatividadeMaterial",
        ),

        migrations.DeleteModel(
            name="AtividadeMaterial",
        ),

        # Nova ordenação do catálogo
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

        # Nova unicidade do catálogo:
        # nome + especificacao + unidade
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
