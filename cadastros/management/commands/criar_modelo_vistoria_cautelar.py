from django.core.management.base import BaseCommand
from django.db import transaction
from cadastros.models import ModeloVistoria, CampoModeloVistoria

CAMPOS = [
('1. Identificação da obra','endereco_obra','Endereço da obra','TEXTO','',True),
('1. Identificação da obra','tipo_obra','Tipo da obra','TEXTO','',False),
('1. Identificação da obra','contratante','Proprietário / Contratante','TEXTO','',True),
('1. Identificação da obra','cpf_contratante','CPF do contratante','TEXTO','',False),
('1. Identificação da obra','pavimentos','Pavimentos previstos','NUMERO','',False),
('1. Identificação da obra','escavacao','Subsolo / Escavação','SIM_NAO','',False),
('1. Identificação da obra','profundidade','Profundidade prevista (m)','NUMERO','',False),
('1. Identificação da obra','responsavel','Responsável técnico','TEXTO','',True),
('1. Identificação da obra','crea','CREA','TEXTO','',False),
('1. Identificação da obra','art_rrt','ART / RRT','TEXTO','',False),
('2. Imóvel vistoriado','data_vistoria','Data da vistoria','DATA','',True),
('2. Imóvel vistoriado','horario','Horário','HORA','',False),
('2. Imóvel vistoriado','acompanhante','Acompanhante','TEXTO','',False),
('2. Imóvel vistoriado','padrao','Padrão construtivo','TEXTO','',False),
('2. Imóvel vistoriado','edificacao','Tipo de edificação','TEXTO','',False),
('2. Imóvel vistoriado','acesso','Acesso','SELECAO','Completo\nParcial\nExterno',True),
('3. Caracterização','descricao_geral','Descrição geral do imóvel','LONGO','',True),
('3. Caracterização','estado','Estado de conservação','SELECAO','Bom\nRegular\nRuim\nPéssimo',True),
('3. Caracterização','observacoes','Observações','LONGO','',False),
('4. Estrutura','estrutura_evidente','Estrutura evidenciada no imóvel?','SIM_NAO','',False),
('4. Estrutura','elementos_estrutura','Elementos estruturais','MULTIPLA','Fundação\nPilares\nLajes / Vigas',False),
('4. Estrutura','descricao_estrutura','Descrição da estrutura','LONGO','',False),
('5. Limitações e conclusão','areas_nao_acessadas','Áreas não acessadas / Limitações','LONGO','',False),
('5. Limitações e conclusão','conclusao','Conclusão técnica complementar','LONGO','',False),
('6. Declaração e assinaturas','declarante','Proprietário / Representante','TEXTO','',True),
('6. Declaração e assinaturas','cpf_declarante','CPF do declarante','TEXTO','',False),
('6. Declaração e assinaturas','quadra','Quadra','TEXTO','',False),
('6. Declaração e assinaturas','lote','Lote','TEXTO','',False),
('6. Declaração e assinaturas','loteamento','Loteamento','TEXTO','',False),
('6. Declaração e assinaturas','vistoriador','Nome do vistoriador','TEXTO','',True),
('6. Declaração e assinaturas','cpf_vistoriador','CPF/CNPJ do vistoriador','TEXTO','',False),
]

class Command(BaseCommand):
    help = 'Cria o modelo base de Vistoria Cautelar de Vizinhança sem duplicar cadastros.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        modelo, created = ModeloVistoria.objects.get_or_create(nome='Vistoria Cautelar de Vizinhança', defaults={'descricao':'Base técnica para registro prévio de imóveis vizinhos.'})
        for index, (secao,chave,titulo,tipo,opcoes,obrigatorio) in enumerate(CAMPOS, 1):
            CampoModeloVistoria.objects.get_or_create(modelo=modelo, chave=chave,
                defaults={'secao':secao,'titulo':titulo,'tipo':tipo,'opcoes':opcoes,'obrigatorio':obrigatorio,'ordem':index})
        self.stdout.write(self.style.SUCCESS(f'Modelo preparado: {modelo.nome} ({len(CAMPOS)} campos).'))
