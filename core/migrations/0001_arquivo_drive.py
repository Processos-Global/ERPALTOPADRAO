from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='ArquivoDrive',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('namespace', models.CharField(max_length=20)),
                ('caminho', models.CharField(max_length=1024)),
                ('caminho_hash', models.CharField(max_length=64, editable=False)),
                ('drive_id', models.CharField(max_length=256)),
                ('tamanho', models.BigIntegerField()),
                ('sha256', models.CharField(max_length=64)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('enviado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(
                        fields=('namespace', 'caminho_hash'),
                        name='saari_drive_caminho_unico',
                    ),
                ],
            },
        ),
    ]
