from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("projetos", "0001_initial"), ("cadastros", "0010_modelos_fvs")]
    operations = [migrations.AddField(model_name="alteracaoprojeto", name="disciplina", field=models.ForeignKey(to="cadastros.checklistprojetogrupo", on_delete=django.db.models.deletion.PROTECT, null=True, blank=True, related_name="alteracoes_projeto"))]
