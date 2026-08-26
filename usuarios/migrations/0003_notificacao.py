from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0002_permissoes_compras"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notificacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=160, verbose_name="Título")),
                ("mensagem", models.CharField(max_length=500, verbose_name="Mensagem")),
                ("modulo", models.CharField(choices=[("SISTEMA", "Sistema"), ("COMPRAS", "Compras"), ("PLANEJAMENTO", "Planejamento")], db_index=True, default="SISTEMA", max_length=30, verbose_name="Módulo")),
                ("tipo", models.CharField(choices=[("INFORMACAO", "Informação"), ("SUCESSO", "Sucesso"), ("ATENCAO", "Atenção"), ("ACAO", "Ação necessária")], db_index=True, default="INFORMACAO", max_length=20, verbose_name="Tipo")),
                ("evento", models.CharField(blank=True, max_length=80, verbose_name="Evento")),
                ("url", models.CharField(blank=True, max_length=500, verbose_name="Destino")),
                ("chave_unica", models.CharField(blank=True, max_length=255, null=True, verbose_name="Chave única")),
                ("dados", models.JSONField(blank=True, default=dict, verbose_name="Dados adicionais")),
                ("lida", models.BooleanField(db_index=True, default=False, verbose_name="Lida")),
                ("lida_em", models.DateTimeField(blank=True, null=True, verbose_name="Lida em")),
                ("criada_em", models.DateTimeField(auto_now_add=True, verbose_name="Criada em")),
                ("atualizada_em", models.DateTimeField(auto_now=True, db_index=True, verbose_name="Atualizada em")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notificacoes_erp", to=settings.AUTH_USER_MODEL, verbose_name="Usuário")),
            ],
            options={
                "verbose_name": "Notificação",
                "verbose_name_plural": "Notificações",
                "ordering": ["-atualizada_em", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="notificacao",
            constraint=models.UniqueConstraint(fields=("usuario", "chave_unica"), name="usuarios_notificacao_usuario_chave_unica"),
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(fields=["usuario", "lida", "atualizada_em"], name="usuarios_notif_user_lida_idx"),
        ),
    ]
