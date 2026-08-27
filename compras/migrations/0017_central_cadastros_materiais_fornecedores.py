from django.db import migrations, models
import django.db.models.deletion


def migrar_fornecedores_e_vincular_materiais(apps, schema_editor):
    FornecedorCompra = apps.get_model("compras", "FornecedorCompra")
    Fornecedor = apps.get_model("cadastros", "Fornecedor")
    Material = apps.get_model("cadastros", "Material")
    NecessidadeCompra = apps.get_model("compras", "NecessidadeCompra")

    # Mantemos o mesmo PK para que todas as FKs e M2Ms existentes possam
    # trocar de tabela sem reescrever os IDs armazenados.
    for antigo in FornecedorCompra.objects.all().order_by("pk"):
        existente_pk = Fornecedor.objects.filter(pk=antigo.pk).first()
        if existente_pk:
            mesmo_documento = (existente_pk.documento or "").strip() == (antigo.documento or "").strip()
            mesmo_nome = (existente_pk.nome or "").strip().casefold() == (antigo.nome or "").strip().casefold()
            if not (mesmo_documento and mesmo_nome):
                raise RuntimeError(
                    "Conflito ao migrar fornecedores: já existe cadastros.Fornecedor "
                    f"com id={antigo.pk}, mas ele não corresponde ao fornecedor legado "
                    f"'{antigo.nome}'. Resolva o conflito antes de executar a migration."
                )
            continue

        # Se o mesmo documento já foi cadastrado manualmente com outro ID,
        # interrompemos para evitar apontar históricos para o fornecedor errado.
        documento = (antigo.documento or "").strip()
        if documento:
            conflito_doc = Fornecedor.objects.filter(documento=documento).exclude(pk=antigo.pk).first()
            if conflito_doc:
                raise RuntimeError(
                    "Conflito ao migrar fornecedores: o documento "
                    f"'{documento}' já pertence a cadastros.Fornecedor id={conflito_doc.pk}. "
                    "Remova/ajuste a duplicidade antes de executar a migration."
                )

        Fornecedor.objects.create(
            pk=antigo.pk,
            codigo=f"FOR-{antigo.pk:06d}",
            nome=(antigo.nome or "").strip(),
            nome_fantasia="",
            documento=documento,
            email=(antigo.email or "").strip(),
            telefone=(antigo.telefone or "").strip(),
            contato="",
            cidade="",
            estado="",
            avaliacao=antigo.avaliacao,
            observacao="Migrado automaticamente do cadastro legado de Compras.",
            ativo=antigo.ativo,
        )

    # Tenta relacionar itens históricos ao catálogo. Se não houver correspondência
    # segura, material permanece NULL; descricao/especificacao/unidade preservam
    # integralmente o histórico.
    aliases_unidade = {
        "UN": ["und", "un", "unidade"],
        "M": ["m"],
        "M2": ["m²", "m2"],
        "M3": ["m³", "m3"],
        "KG": ["kg"],
        "T": ["t", "ton"],
        "L": ["l", "L"],
        "SC": ["saco", "sc"],
        "CX": ["cx", "caixa"],
        "PC": ["pc", "peça", "peca"],
        "GL": ["gl", "galão", "galao"],
        "RL": ["rl", "rolo"],
        "PT": ["pt", "pacote"],
        "VB": ["vb"],
    }

    for necessidade in NecessidadeCompra.objects.filter(material__isnull=True).iterator():
        nome = (necessidade.descricao or "").strip()
        especificacao = (necessidade.especificacao or "").strip()
        unidades = aliases_unidade.get((necessidade.unidade or "").strip().upper(), [necessidade.unidade])
        qs = Material.objects.filter(nome__iexact=nome, unidade__sigla__in=unidades)
        if especificacao:
            qs = qs.filter(especificacao__iexact=especificacao)
        candidatos = list(qs[:2])
        if len(candidatos) == 1:
            necessidade.material_id = candidatos[0].pk
            necessidade.save(update_fields=["material"])


def reverse_sem_recriar_legado(apps, schema_editor):
    # A reversão estrutural recriará FornecedorCompra pelo estado da migration,
    # mas não tentamos reconstruir dados automaticamente para evitar perda ou
    # mistura de alterações feitas depois da migração.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0002_alter_fornecedor_avaliacao"),
        ("compras", "0016_fluxo_individual_fornecedor"),
    ]

    operations = [
        migrations.AddField(
            model_name="necessidadecompra",
            name="material",
            field=models.ForeignKey(
                blank=True,
                help_text="Material do catálogo central. Obrigatório para novas compras.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="necessidades_compra",
                to="cadastros.material",
            ),
        ),
        migrations.RunPython(
            migrar_fornecedores_e_vincular_materiais,
            reverse_code=reverse_sem_recriar_legado,
        ),
        migrations.AlterField(
            model_name="processocompra",
            name="fornecedores_sugeridos",
            field=models.ManyToManyField(
                blank=True,
                help_text="Fornecedores indicados no pedido inicial para orientar o Suprimentos.",
                related_name="processos_compra_sugeridos",
                to="cadastros.fornecedor",
            ),
        ),
        migrations.AlterField(
            model_name="solicitacaocotacaofornecedor",
            name="fornecedor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="solicitacoes_cotacao",
                to="cadastros.fornecedor",
            ),
        ),
        migrations.AlterField(
            model_name="cotacaofornecedor",
            name="fornecedor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cotacoes",
                to="cadastros.fornecedor",
            ),
        ),
        migrations.AlterField(
            model_name="contratacaocompra",
            name="fornecedor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contratacoes",
                to="cadastros.fornecedor",
            ),
        ),
        migrations.AlterField(
            model_name="pedidocompra",
            name="fornecedor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pedidos",
                to="cadastros.fornecedor",
            ),
        ),
        migrations.DeleteModel(
            name="FornecedorCompra",
        ),
    ]
