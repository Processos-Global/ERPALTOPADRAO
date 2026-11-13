from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0009_preferencias_email_compras"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="PermissaoAcao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modulo", models.CharField(max_length=30)),
                ("acao", models.CharField(max_length=70)),
                ("permitido", models.BooleanField(default=False)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permissoes_acoes_erp", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Permissão de ação", "verbose_name_plural": "Permissões de ações"},
        ),
        migrations.AddConstraint(model_name="permissaoacao", constraint=models.UniqueConstraint(fields=("usuario", "modulo", "acao"), name="usr_acao_usuario_modulo_acao_un")),
        migrations.AddIndex(model_name="permissaoacao", index=models.Index(fields=["usuario", "modulo"], name="usr_acao_usr_mod_idx")),
    ]
