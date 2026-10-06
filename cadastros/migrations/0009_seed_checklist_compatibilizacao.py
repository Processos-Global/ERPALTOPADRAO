from django.db import migrations

DADOS = {'PAISAGISMO': [('A1', '1.1', 'Projeto Preliminar - PDF'), ('A1', '1.1', 'Projeto Preliminar - DWG'), ('A1', '1.2', 'Vídeo Preliminar'), ('A2', '2.1', 'Projeto Executivo - PDF'), ('A2', '2.2', 'Projeto Executivo - DWG'), ('A2', '2.1', 'Vídeo Executivo')], 'ARQ': [('A0', '0.0', 'Programa de necessidades / Contrato'), ('A1', '1.1', 'Layout / Quadro de áreas / Norte'), ('A1', '1.2', 'PowerPoint – apresentação do estudo preliminar / programa / cota de soleira'), ('A1', '1.3', 'Vídeo ou imagens renderizadas (IA)'), ('A2', '2.1', 'Anteprojeto para cálculo'), ('A2', '2.2', 'Reunião técnica com fornecedores / construtora / calculista / ata'), ('A2', '2.3', 'Enviar lista de fornecedores escolhidos para o cliente'), ('A2', '2.4', 'PowerPoint 3D arquitetura / fachadas / piscina / escadas / muro'), ('A2', '2.5', 'Briefing áreas molhadas e revestimentos gerais'), ('A2', '2.6', 'Briefing ar-condicionado e esquadrias'), ('A3', '3.1', 'Situação / ocupação / cobertura / detalhes'), ('A3', '3.2', 'Planta dos pavimentos'), ('A3', '3.3', 'Cortes e fachadas detalhadas'), ('A3', '3.4', 'Quadro de esquadrias e portas'), ('A3', '3.5', 'Projeto de aprovação / RRT'), ('A3', '', 'Solicitar ao administrativo placa na obra, se aplicável'), ('A4', '4.1', 'Planta – eixos hidráulicos'), ('A4', '4.2', 'Planta – tomadas'), ('A4', '4.3', 'Planta – forros com detalhes e estudo luminotécnico'), ('A4', '4.4', 'Compatibilizar planta de forro com iluminação especializada aprovada'), ('A4', '4.5', 'Compatibilizar executivo e instalações com a estrutura'), ('A5', '5.1', 'Vistas de esquadrias / quadro / detalhes / mapa-chave'), ('A5', '5.2', 'Vistas de portas e painéis / quadro / detalhes / mapa-chave'), ('A5', '5.3', 'Escadas e guarda-corpos'), ('A5', '5.4', "Piscina / SPA / ducha / espelho d'água / fire place"), ('A5', '5.5', 'Muro / portão / guarita'), ('A5', '5.6', 'Marcenaria decorativa'), ('A6', '6.1', 'PowerPoint – mapa de pisos'), ('A6', '6.2', 'PowerPoint 3D – áreas molhadas'), ('A6', '6.3', 'PowerPoint 3D – banheiros'), ('A6', '6.4', 'Compatibilizar planta de eixos hidráulicos'), ('A6', '', 'Atualização e entrega do 3D e vídeo, se houver – aprovados'), ('A7', '7.1', 'PowerPoint 3D – vistas internas de painéis e arremates'), ('A7', '7.2', 'Detalhamento de pisos / soleiras / rodapés / peitoris / elevador'), ('A7', '7.3', 'Detalhamento dos banheiros'), ('A7', '7.4', 'Detalhamento das áreas molhadas e áreas de apoio'), ('A7', '7.5', 'Compatibilização com o projeto de planejados'), ('A8', '8.1', 'Memorial descritivo com especificações de arquitetura'), ('A8', '8.2', 'Compatibilizar tomadas e iluminação com a decoração'), ('A8', '8.3', 'Dar baixa na RRT após recebimento do Habite-se'), ('A8', '8.4', 'Solicitar remoção da placa da obra'), ('Decoração', '', 'Revisão de layout'), ('Decoração', '', 'Briefing de decoração'), ('Decoração', '', 'Apresentação de decoração, marcenaria e mobiliário'), ('Decoração', '', 'Detalhamento de marcenaria'), ('Decoração', '', 'Reunião com cliente / loja de planejados ou marceneiro'), ('Decoração', '', 'Memorial com especificações de decoração'), ('Decoração', '', 'Reunião com cliente nas lojas / especificação de móveis'), ('Decoração', '', 'Acabamentos de mobiliário / papel de parede / cortinas')], 'ESTRUTURA': [('A0', '0.0', 'Laudo de sondagem  (SPT)'), ('A1', '1.1', 'Projeto de Topografia'), ('A2', '2.0', 'Projeto de Infraestrutura (Fundações)'), ('A2', '2.1', 'Planta de locação da fundação'), ('A2', '2.2', 'Planta de armação'), ('A2', '2.3', 'Planta de vigas baldrames'), ('A3', '3.0', 'Projetos de Supeestrutura'), ('A3', '3.1', 'Planta de locação dos Pilares'), ('A3', '3.2', 'Planta de locação dos Vigas'), ('A3', '3.3', 'Planta de locação dos lajes'), ('A3', '3.4', 'Planta da formas dos pavimentos'), ('A3', '3.5', 'Planta das Armações dos pilares'), ('A3', '3.6', 'Planta das Armações dos vigas'), ('A3', '3.7', 'Planta de Armação das lajes'), ('A4', '4.0', 'Projetos Estruturais Complementares'), ('A4', '4.1', 'Projetos de escadas ou rampas'), ('A4', '4.2', 'Projeto do detalhamento de Piscinas'), ('A4', '4.3', 'Projeto de Muro de Arrimo e Contenções')], 'INSTALAÇÕES': [('A1', '1.0', 'Projeto Eletrico'), ('A1', '1.1', 'Projeto Luminotecnico'), ('A1', '1.2', 'Locação de tomadas'), ('A1', '1.3', 'Locação de Iluminação'), ('A1', '1.4', 'Planta Baixa Equipamentos'), ('A1', '1.5', 'Planta de Detalhamento Elétrico'), ('A1', '1.6', 'Planta Diagrama Unifilar'), ('A1', '1.7', 'Projetos de Quadros de Cargas e Detalhamentos'), ('A1', '1.8', 'Projeto de Quadros de Automação'), ('A1', '1.9', 'Projeto de Infraestrutura geral'), ('A1', '1.10', 'Projeto de Automação de Iluminação'), ('A1', '1.11', 'Projeto de Automação de Sistemas'), ('A1', '1.12', 'Projeto de Automação de Rede'), ('A1', '1.13', 'Projeto de Automação de Ar Condicionado'), ('A1', '1.14', 'Projeto de Pulsadores'), ('A1', '1.15', 'Projeto eletrico - Alteração do padrão de energia para fotovoltaica'), ('A2', '2.0', 'Projeto de SPDA'), ('A2', '2.1', 'Planta Baixa  SPDA dos Subsistema'), ('A2', '2.2', 'Planta de Detalhamento de SPDA e Aterramento'), ('A3', '3.0', 'Projeto de Conectividade'), ('A3', '3.1', 'Projeto de CFTV,  Alarme e Controle de Acesso'), ('A3', '3.1.2', 'Planta Baixa'), ('A4', '3.1.3', 'Planta de cabeamento'), ('A4', '3.1.4', 'Detalhamento de projeto ( quadros, rack, ternimais, etc.)'), ('A4', '3.1.5', 'Planta de infraestrutura'), ('A4', '3.2', 'Projeto de Rede'), ('A4', '3.2.1', 'Planta Baixa'), ('A5', '3.2.2', 'Planta de cabeamento'), ('A5', '3.2.3', 'Detalhamento de projeto ( quadros, rack, ternimais, etc.)'), ('A5', '3.3', 'Projeto de Sonorização'), ('A6', '3.3.1', 'Planta Baixa'), ('A6', '3.3.2', 'Planta de cabeamento'), ('A6', '3.3.3', 'Detalhamento de projeto ( quadros, rack, ternimais, etc.)'), ('A7', '4.0', 'Projetos Hidraulicos'), ('A7', '4.1', 'Planta Baixa'), ('A7', '4.2', 'Planta de Detalhado ( isometricos, barriletes, vistas, conecções especiais, etc.)'), ('A7', '4.3', 'Planta Baixa Hidromecânica Piscina'), ('A8', '5.0', 'Projeto Sanitarios e Ventilação'), ('A8', '5.1', 'Planta Baixa'), ('A8', '5.2', 'Planta de detalhado ( isometricos, vistas, conecções especiais, caixas de passagens, etc.)'), ('A9', '6.0', 'Projeto Pluvial'), ('A9', '6.1', 'Planta Baixa'), ('A9', '6.2', 'Projeto de detalhado ( isometricos, vistas, conecções especiais, caixas de passagens, etc.)'), ('A10', '7.0', 'Projeto de Ar Condicionado'), ('A10', '7.1', 'Planta baixa'), ('A10', '7.2', 'Planta de Detalhamento  ( isometricos, vistas, conecções especiais, equipamentos, etc.)')], 'FOTOVOLTAICO': [('A1', '1.0', 'Projeto Fotovoltaico'), ('A1', '1.1', 'Planta Baixa'), ('A1', '1.2', 'Planta de Detalhado ( isometricos, barriletes, vistas, conecções especiais, etc.)')], 'ILUMINAÇÃO': [('A0', '0.0', 'Projeto Preliminar - PDF'), ('A1', '1.1', 'Projeto Preliminar - DWG'), ('A1', '2.0', 'Projeto de Iluminação ( locação)'), ('A1', '2.1', 'Planta de Seções'), ('A2', '2.2', 'Caderno de Detalhamento de Gesso e Marcenaria'), ('A2', '2.3', 'Caderno de Especificações Técnica')]}

SLUGS = {'PAISAGISMO': 'paisagismo', 'ARQ': 'arquitetura', 'ESTRUTURA': 'estrutura', 'INSTALAÇÕES': 'instalacoes', 'FOTOVOLTAICO': 'fotovoltaico', 'ILUMINAÇÃO': 'iluminacao'}
NOMES = {'PAISAGISMO': 'Paisagismo', 'ARQ': 'Arquitetura', 'ESTRUTURA': 'Estrutura', 'INSTALAÇÕES': 'Instalações', 'FOTOVOLTAICO': 'Fotovoltaico', 'ILUMINAÇÃO': 'Iluminação'}


def carregar_planilha(apps, schema_editor):
    Grupo = apps.get_model("cadastros", "ChecklistProjetoGrupo")
    Item = apps.get_model("cadastros", "ChecklistProjetoItem")

    for ordem_grupo, (aba, linhas) in enumerate(DADOS.items(), start=1):
        grupo, _ = Grupo.objects.update_or_create(
            tipo="COMPATIBILIZACAO",
            slug=SLUGS[aba],
            defaults={"nome": NOMES[aba], "ordem": ordem_grupo, "ativo": True},
        )
        for ordem_item, (etapa, codigo, atividade) in enumerate(linhas, start=1):
            Item.objects.get_or_create(
                grupo=grupo,
                ordem=ordem_item,
                defaults={
                    "etapa": etapa,
                    "codigo": codigo,
                    "entrega_atividade": atividade,
                    "ativo": True,
                },
            )


def remover_seed(apps, schema_editor):
    Grupo = apps.get_model("cadastros", "ChecklistProjetoGrupo")
    Grupo.objects.filter(tipo="COMPATIBILIZACAO", slug__in=list(SLUGS.values())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0008_checklist_projetos"),
    ]

    operations = [
        migrations.RunPython(carregar_planilha, remover_seed),
    ]
