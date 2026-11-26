from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("compras", "0042_contratacaocompra_marcador_ativa")]

    operations = [
        migrations.AddConstraint(
            model_name="contratacaocompra",
            constraint=models.UniqueConstraint(
                fields=("processo", "fornecedor", "marcador_ativa"),
                name="comp_contratacao_ativa_uniq",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="contratacaocompra",
            name="comp_contrat_proc_forn_ativa_uniq",
        ),
    ]
