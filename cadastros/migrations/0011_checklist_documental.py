from django.db import migrations, models

DOCUMENTOS = [
    "DEMOLIÇÃO E CNO",
    "AVERBAÇÃO DE DEMOLIÇÃO",
    "ALVARÁ",
    "CNO DE ALVARÁ",
    "HABITE-SE",
    "CND INSS",
    "AVERBAÇÃO DA CONSTRUÇÃO",
]


def carregar_documentos(apps, schema_editor):
    Grupo = apps.get_model("cadastros", "ChecklistProjetoGrupo")
    Item = apps.get_model("cadastros", "ChecklistProjetoItem")
    grupo, _ = Grupo.objects.get_or_create(
        tipo="DOCUMENTAL", slug="documentacao-da-obra",
        defaults={"nome": "Documentação da obra", "ordem": 1, "ativo": True},
    )
    for ordem, nome in enumerate(DOCUMENTOS, 1):
        Item.objects.get_or_create(
            grupo=grupo, entrega_atividade=nome,
            defaults={"ordem": ordem, "ativo": True},
        )


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0010_modelos_fvs")]
    operations = [
        migrations.AlterField(
            model_name="checklistprojetogrupo", name="tipo",
            field=models.CharField(max_length=30, choices=[
                ("COMPATIBILIZACAO", "Acompanhamento de Projetos"),
                ("DOCUMENTAL", "Checklist Documental"),
            ]),
        ),
        migrations.RunPython(carregar_documentos, migrations.RunPython.noop),
    ]
