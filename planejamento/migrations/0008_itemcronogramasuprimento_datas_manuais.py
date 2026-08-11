from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("planejamento", "0007_itemcronogramasuprimento_data_real_contratacao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="datas_editadas_manualmente",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="datas_editadas_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="datas_editadas_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="itens_cronograma_suprimentos_editados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
