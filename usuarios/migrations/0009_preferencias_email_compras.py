from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0008_limpar_colunas_legadas_permissaofinanceiro"),
    ]

    operations = [
        migrations.AddField(
            model_name="permissaocompras",
            name="receber_emails",
            field=models.BooleanField(
                default=True,
                help_text="Controla somente os e-mails. As notificações dentro do ERP continuam funcionando.",
                verbose_name="Receber e-mails de Compras",
            ),
        ),
        migrations.AddField(model_name="permissaocompras", name="email_visualizar", field=models.BooleanField(default=True, verbose_name="E-mail: avisos gerais de Compras")),
        migrations.AddField(model_name="permissaocompras", name="email_solicitar_compra", field=models.BooleanField(default=True, verbose_name="E-mail: solicitação de compra")),
        migrations.AddField(model_name="permissaocompras", name="email_executar_cotacao", field=models.BooleanField(default=True, verbose_name="E-mail: cotação")),
        migrations.AddField(model_name="permissaocompras", name="email_compatibilizar", field=models.BooleanField(default=True, verbose_name="E-mail: compatibilização")),
        migrations.AddField(model_name="permissaocompras", name="email_negociar", field=models.BooleanField(default=True, verbose_name="E-mail: negociação")),
        migrations.AddField(model_name="permissaocompras", name="email_aprovar_compra", field=models.BooleanField(default=True, verbose_name="E-mail: aprovação")),
        migrations.AddField(model_name="permissaocompras", name="email_gerenciar_pedidos", field=models.BooleanField(default=True, verbose_name="E-mail: pedidos")),
        migrations.AddField(model_name="permissaocompras", name="email_receber_pedidos", field=models.BooleanField(default=True, verbose_name="E-mail: recebimentos")),
        migrations.AddField(model_name="permissaocompras", name="email_cancelar_pedidos", field=models.BooleanField(default=True, verbose_name="E-mail: cancelamentos")),
        migrations.AddField(model_name="permissaocompras", name="email_administrar", field=models.BooleanField(default=True, verbose_name="E-mail: administração de Compras")),
    ]
