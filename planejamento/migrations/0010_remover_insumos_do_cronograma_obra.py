from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0004_refatoracao_origem_itens_compra"),
        ("planejamento", "0009_itemcronogramasuprimento_datas_realizadas"),
    ]

    operations = [
        migrations.DeleteModel(name="SuprimentoAtividade"),
        migrations.DeleteModel(name="InsumoPlanejamento"),
    ]
