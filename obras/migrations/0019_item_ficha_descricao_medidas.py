from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("obras", "0018_diario_atividades")]

    operations = [
        migrations.AddField(
            model_name="itemfichatecnica",
            name="descricao_medidas",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="itemfichatecnica", name="material",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.PROTECT,
                                    related_name="itens_fichas_tecnicas", to="cadastros.material"),
        ),
    ]
