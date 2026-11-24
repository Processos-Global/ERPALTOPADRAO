from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0015_solicitacao_avulsa_idempotente")]

    operations = [
        migrations.CreateModel(
            name="ProgramacaoPagamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_programada", models.DateField(db_index=True)),
                ("ciclo_aprovacao", models.PositiveIntegerField()),
                ("ativa", models.BooleanField(default=True)),
                ("titulo", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="programacao_pagamento", to="financeiro.titulopagar")),
            ],
        ),
    ]
