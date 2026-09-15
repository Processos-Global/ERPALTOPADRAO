import unicodedata

from django.db import migrations


def _normalizar(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii").upper().strip()


def reclassificar(apps, schema_editor):
    Item = apps.get_model("planejamento", "ItemCronogramaSuprimento")
    for item in Item.objects.all().only("id", "categoria", "tipo_fluxo_compra").iterator():
        categoria = _normalizar(item.categoria)
        if not categoria or ("MATERIA" in categoria and "VARIAD" in categoria):
            novo = "NORMAL"
        else:
            novo = "GRANDE_FORNECEDOR"
        if item.tipo_fluxo_compra != novo:
            Item.objects.filter(pk=item.pk).update(tipo_fluxo_compra=novo)


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0013_corrigir_padrao_fluxo_compra_normal"),
    ]

    operations = [
        migrations.RunPython(reclassificar, migrations.RunPython.noop),
    ]
