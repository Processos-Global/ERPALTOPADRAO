from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0015_modelo_vistoria")]

    operations = [
        migrations.AddField(
            model_name="tipoitemgrandefornecedor",
            name="tipos_ambiente_sugeridos",
            field=models.ManyToManyField(
                blank=True,
                help_text="Sugestão opcional para ambientes deste tipo; a ficha só recebe itens após confirmação.",
                related_name="itens_gf_sugeridos",
                to="cadastros.tipoambiente",
            ),
        ),
    ]
