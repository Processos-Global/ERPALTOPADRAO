from django.db import migrations, models


def atualizar_status_documental(apps, schema_editor):
    Resposta = apps.get_model("projetos", "ChecklistProjetoResposta")
    mapeamento = {
        "NAO_RECEBIDO": "INICIADO",
        "PARCIALMENTE": "EM_ANDAMENTO",
        "RECEBIDO": "FINALIZADO",
    }
    for antigo, novo in mapeamento.items():
        Resposta.objects.filter(
            item__grupo__tipo="DOCUMENTAL", status=antigo
        ).update(status=novo)


def reverter_status_documental(apps, schema_editor):
    Resposta = apps.get_model("projetos", "ChecklistProjetoResposta")
    mapeamento = {
        "INICIADO": "NAO_RECEBIDO",
        "EM_ANDAMENTO": "PARCIALMENTE",
        "FINALIZADO": "RECEBIDO",
    }
    for antigo, novo in mapeamento.items():
        Resposta.objects.filter(
            item__grupo__tipo="DOCUMENTAL", status=antigo
        ).update(status=novo)


class Migration(migrations.Migration):
    dependencies = [("projetos", "0002_alteracaoprojeto_disciplina")]
    operations = [
        migrations.AlterField(
            model_name="checklistprojetoresposta",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("INICIADO", "Iniciado"),
                    ("EM_ANDAMENTO", "Em andamento"),
                    ("FINALIZADO", "Finalizado"),
                    ("NAO_RECEBIDO", "Não Recebido"),
                    ("PARCIALMENTE", "Parcialmente"),
                    ("RECEBIDO", "Recebido"),
                    ("NAO_SE_APLICA", "Não se aplica"),
                ],
                default="NAO_RECEBIDO",
            ),
        ),
        migrations.RunPython(atualizar_status_documental, reverter_status_documental),
    ]
