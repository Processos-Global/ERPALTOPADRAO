from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("compras", "0033_processo_compra_avulsa"), ("cadastros", "0006_alter_caracteristicaambiente_options_and_more")]
    operations = [
        migrations.AddField(
            model_name="rateioparcelagrandefornecedor", name="fornecedor",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="rateios_grande_fornecedor", to="cadastros.fornecedor"),
        ),
        migrations.AddField(
            model_name="rateioparcelagrandefornecedor", name="data_vencimento",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="rateioparcelagrandefornecedor", name="beneficiario_nome", field=models.CharField(blank=True, max_length=255),
        ),
    ]
