from django.db import migrations, models
import core.storage


class Migration(migrations.Migration):
    dependencies = [('pos_obra', '0001_initial')]
    operations = [
        migrations.AlterField(
            model_name='anexochamado',
            name='arquivo',
            field=models.FileField(storage=core.storage.PrivateMediaStorage(), upload_to='pos_obra/%Y/%m/'),
        ),
    ]
