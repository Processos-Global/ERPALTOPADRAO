from django.db import migrations, models
import django.db.models.deletion


def carregar_base(apps, schema_editor):
    Caracteristica = apps.get_model("cadastros", "CaracteristicaAmbiente")
    TipoPavimento = apps.get_model("cadastros", "TipoPavimento")
    TipoAmbiente = apps.get_model("cadastros", "TipoAmbiente")
    Categoria = apps.get_model("cadastros", "CategoriaGrandeFornecedor")
    TipoItem = apps.get_model("cadastros", "TipoItemGrandeFornecedor")
    Opcao = apps.get_model("cadastros", "OpcaoEspecificacaoGrandeFornecedor")

    seco, _ = Caracteristica.objects.get_or_create(codigo="SECO", defaults={"nome": "Seco", "ativo": True})
    molhado, _ = Caracteristica.objects.get_or_create(codigo="AREA_MOLHADA", defaults={"nome": "Área Molhada", "ativo": True})
    Caracteristica.objects.get_or_create(codigo="EXTERNO", defaults={"nome": "Externo", "ativo": True})
    Caracteristica.objects.get_or_create(codigo="TECNICO", defaults={"nome": "Técnico", "ativo": True})

    for nome, ordem in [('SUBSOLO', 1), ('TÉRREO', 2), ('1º PAVIMENTO', 3), ('COBERTURA', 4)]:
        TipoPavimento.objects.get_or_create(nome=nome, defaults={"ordem": ordem, "ativo": True})

    for nome, area_molhada in [('ACADEMIA', True), ('ADEGA', False), ('AREA DE SERVIÇO', True), ('BRINQUEDOTECA', False), ('CALÇADA', False), ('CANIL', True), ('CASA DE MÁQUINAS', False), ('CIRCULAÇÃO', False), ('CLOSET SUÍTE MASTER', False), ('COPA', True), ('COZINHA', True), ('COZINHA AUXILIAR', True), ('CPD', False), ('DEPENDÊNCIA', False), ('DEPOSITO', False), ('DML', False), ('ELEVADOR', False), ('ESCADA SERVIÇO', False), ('ESCADA SOCIAL', False), ('ESCRITORIO', False), ('ESTAR INTIMO', False), ('GARAGEM', False), ('GOURMET', True), ('GUARITA', True), ('HALL DE ENTRADA', False), ('HOME', False), ('JARDIM', True), ('JARDIM INTERNO', False), ('LAVABO', True), ('LOUCEIRO', False), ('MALEIRO', False), ('MURO FRONTAL', False), ('MURO PERIMETRO (U)', False), ('PASSEIO EXTERNO', False), ('PISCINA', False), ('QUADRA', False), ('QUARTO', False), ('QUARTO MOTORISTA', False), ('RAMPA', True), ('ROOFTOP', False), ('ROUPEIRO', False), ('SALA DE ESTAR', False), ('SALA DE JANTAR', False), ('SALA DE JOGOS', False), ('SALA INTIMA', False), ('SALÃO', False), ('SAUNA', True), ('SPA', True), ('SUÍTE', False), ('SUÍTE MASTER', False), ('VARANDA FRONTAL', False), ('VARANDA POSTERIOR', False), ('WC', True), ('WC BRINQUEDOTECA', True), ('WC GUARITA', True), ('WC MOTORISTA', True), ('WC SALÃO DE JOGOS', True), ('WC SERVIÇO', True), ('WC SUÍTE', True), ('WC SUÍTE MASTER', True), ('ÁREA DE SERVIÇO', True), ('ÁREA TECNICA', True)]:
        TipoAmbiente.objects.get_or_create(
            nome=nome,
            defaults={"caracteristica_padrao": molhado if area_molhada else seco, "ativo": True},
        )

    for ordem, (nome, regra, somente_molhada) in enumerate([('AR CONDICIONADO - EQUIPAMENTO', 'MULTIPLA_PROJETO', False), ('AR CONDICIONADO - SISTEMA', 'MULTIPLA_AMBIENTE', False), ('AUTOMAÇÃO', 'MULTIPLA_PROJETO', False), ('FUNDAÇÃO', 'SIM_NAO_PROJETO', False), ('ILUMINAÇÃO', 'SIM_NAO_PROJETO', False), ('PROTENSÃO', 'SIM_NAO_PROJETO', False), ('ELEVADOR', 'SIM_NAO_PROJETO', False), ('ESQUADRIAS', 'MULTIPLA_AMBIENTE', False), ('PORTAS', 'SIM_NAO_AMBIENTE', False), ('MARMORARIA', 'MULTIPLA_AMBIENTE', False), ('MARCENARIA DECORATIVA', 'MULTIPLA_AMBIENTE', False), ('QUADROS ELETRICOS', 'DESCRITIVO', False), ('PISO E FORRO DE MADEIRA', 'MULTIPLA_AMBIENTE', False), ('PAISAGISMO', 'SIM_NAO_PROJETO', False), ('IRRIGAÇÃO', 'SIM_NAO_PROJETO', False), ('LOUÇAS E METAIS', 'MULTIPLA_AMBIENTE', True), ('VIDROS E ESPELHOS', 'MULTIPLA_AMBIENTE', False), ('ELETRODOMESTICOS', 'SIM_NAO_PROJETO', False), ('RALOS LINEARES', 'SIM_NAO_PROJETO', False), ('COIFA BOX', 'SIM_NAO_PROJETO', False), ('ADEGA', 'SIM_NAO_PROJETO', False), ('AQUECIMENTO PISCINA', 'SIM_NAO_PROJETO', False)], start=1):
        Categoria.objects.get_or_create(
            nome=nome,
            defaults={"tipo_preenchimento": regra, "somente_area_molhada": somente_molhada, "ordem": ordem, "ativo": True},
        )

    itens_por_categoria = {'AR CONDICIONADO - EQUIPAMENTO': ['DUTADO', 'VRF', 'SPLIT', 'MULTI SPLIT'], 'AR CONDICIONADO - SISTEMA': ['DIFUSOR', 'CASSETE 1 VIA', 'CASSETE 4 VIAS', 'HI-WALL'], 'AUTOMAÇÃO': ['ALARME', 'CONTROLE DE ACESSO', 'REDE', 'PULSADORES', 'INFRA DE AUTOMAÇÃO', 'CFTV'], 'ESQUADRIAS': ['GUARDA CORPO', 'CLARABOIA', 'JANELA BASCULANTE', 'JANELA DE CORRER', 'BRISES', 'PAINEL MUXARABI', 'PORTA DE CORRER', 'PORTA PIVOTANTE', 'RIPADO', 'JANELA FIXA', 'PORTA CAMARÃO'], 'MARMORARIA': ['PEITORIL', 'SOLEIRA', 'PISO', 'PAREDE', 'NICHOS', 'BANCADAS', 'RODAPÉ', 'FILETES', 'ARREMATE', 'BORDA PISCINA'], 'MARCENARIA DECORATIVA': ['PAINEIS', 'PISO', 'FORRO', 'PORTAS', 'ARMARIOS', 'MUXARABI', 'RIPADOS', 'PRATILEIRA', 'BRISE', 'ADEGA'], 'PISO E FORRO DE MADEIRA': ['FORRO', 'PISO'], 'LOUÇAS E METAIS': ['TORNEIRA', 'TORNEIRA MONOCOMANDO', 'CHUVEIRO', 'BACIA SANITÁRIA', 'DUCHA', 'PORTA PAPEL HIGIENICO', 'RALO', 'TANQUE', 'CUBA', 'RALO OCULTO', 'VALVULA', 'CABIDEIRO', 'PAPELEIRA', 'TOALHEIRO BARRA', 'TOALHEIRO GANCHO', 'ACABAMENTO DE REGISTRO', 'BANHEIRA', 'BICA', 'SIFÃO METÁLICO'], 'VIDROS E ESPELHOS': ['ESPELHO', 'BOX']}
    for categoria_nome, itens in itens_por_categoria.items():
        categoria = Categoria.objects.get(nome=categoria_nome)
        for ordem, nome in enumerate(itens, start=1):
            TipoItem.objects.get_or_create(categoria=categoria, nome=nome, defaults={"ordem": ordem, "ativo": True})

    marmoraria = Categoria.objects.get(nome="MARMORARIA")
    for ordem, nome in enumerate(['Mármore Travertino Romano - Bruto', 'Mármore Travertino Romano - Resinado', 'Mármore Travertino Romano -  Levigado', 'Mármore Bege Bahia - Bruto', 'Mármore Bege Bahia- Resinado', 'Mármore Bege Bahia- Levigado', 'Granito Preto São Gabriel-  Flameado', 'Granito Preto São Gabriel- Polido', 'Granito Preto São Gabriel- Escovado', 'Granito Cinza Andorinha -  Flameado', 'Granito Cinza Andorinha- Polido', 'Granito Cinza Andorinha- Escovado', 'Granito Verde Ubatuba- Flameado', 'Granito Verde Ubatuba- Polido', 'Granito Verde Ubatuba- Escovado', 'Granito Preto Absoluto - Escovado', 'Granito Preto Absoluto- Flameado', 'Granito Preto Absoluto- Polido', 'Quartzito Wadanda', 'Quartzito', 'Pedra São Tomé', 'Pedra Portuguesa', 'Pedra Macaquino', 'Pedra Moledo', 'Dekton', 'Silestone'], start=1):
        Opcao.objects.get_or_create(
            categoria=marmoraria, tipo_item=None, nome=nome,
            defaults={"ordem": ordem, "ativo": True},
        )


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0003_remover_atividade_subatividade_material")]
    operations = [
        migrations.CreateModel(
            name="CaracteristicaAmbiente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("codigo", models.CharField(max_length=40, unique=True)),
                ("nome", models.CharField(max_length=100, unique=True)),
            ],
            options={"ordering": ("nome",)},
        ),
        migrations.CreateModel(
            name="TipoPavimento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=100, unique=True)),
                ("ordem", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("ordem", "nome")},
        ),
        migrations.CreateModel(
            name="CategoriaGrandeFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=160, unique=True)),
                ("tipo_preenchimento", models.CharField(choices=[("MULTIPLA_PROJETO", "Múltipla escolha - projeto"), ("MULTIPLA_AMBIENTE", "Múltipla escolha - por ambiente"), ("SIM_NAO_PROJETO", "Sim/Não - no projeto"), ("SIM_NAO_AMBIENTE", "Sim/Não - por ambiente"), ("DESCRITIVO", "Descritivo - aberto")], default="MULTIPLA_AMBIENTE", max_length=30)),
                ("somente_area_molhada", models.BooleanField(default=False)),
                ("ordem", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("ordem", "nome")},
        ),
        migrations.CreateModel(
            name="TipoAmbiente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=140, unique=True)),
                ("caracteristica_padrao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tipos_ambiente", to="cadastros.caracteristicaambiente")),
            ],
            options={"ordering": ("nome",)},
        ),
        migrations.CreateModel(
            name="TipoItemGrandeFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=160)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("categoria", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tipos_itens", to="cadastros.categoriagrandefornecedor")),
                ("unidade_padrao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tipos_itens_grande_fornecedor", to="cadastros.unidademedida")),
            ],
            options={"ordering": ("categoria__ordem", "ordem", "nome")},
        ),
        migrations.CreateModel(
            name="OpcaoEspecificacaoGrandeFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=220)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("categoria", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="opcoes_especificacao", to="cadastros.categoriagrandefornecedor")),
                ("tipo_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="opcoes_especificacao", to="cadastros.tipoitemgrandefornecedor")),
            ],
            options={"ordering": ("categoria__ordem", "ordem", "nome")},
        ),
        migrations.AddConstraint(
            model_name="tipoitemgrandefornecedor",
            constraint=models.UniqueConstraint(fields=("categoria", "nome"), name="cad_tipo_item_gf_cat_nome_uniq"),
        ),
        migrations.AddConstraint(
            model_name="opcaoespecificacaograndefornecedor",
            constraint=models.UniqueConstraint(fields=("categoria", "tipo_item", "nome"), name="cad_opcao_esp_gf_uniq"),
        ),
        migrations.RunPython(carregar_base, migrations.RunPython.noop),
    ]
