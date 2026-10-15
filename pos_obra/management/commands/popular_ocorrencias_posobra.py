from django.core.management.base import BaseCommand
from cadastros.models import CategoriaOcorrencia,TipoProblema
DADOS={
'Hidráulica':['Vazamento','Entupimento','Baixa pressão','Falta de água'],
'Elétrica':['Tomada sem funcionamento','Disjuntor desarmando','Iluminação','Curto-circuito'],
'Impermeabilização':['Infiltração','Umidade','Falha de vedação'],
'Pintura':['Descascamento','Manchas','Bolhas'],
'Revestimentos':['Trinca','Peça solta','Rejunte deteriorado'],
'Esquadrias':['Porta desalinhada','Janela sem vedação','Fechadura'],
'Cobertura':['Goteira','Calha','Telha'],
'Forro e gesso':['Fissura','Mancha','Deslocamento'],
'Estrutura e alvenaria':['Trinca','Fissura','Deformação aparente'],
'Louças e metais':['Torneira','Descarga','Vaso sanitário'],
'Pisos':['Desnivelamento','Caimento','Peça solta'],
'Piscina':['Vazamento','Revestimento','Equipamentos'],
'Áreas externas':['Drenagem','Pavimentação','Jardim'],
'Outros':['Problema não listado']}
class Command(BaseCommand):
    help='Cria catálogo inicial de problemas sem apagar registros existentes.'
    def handle(self,*args,**opts):
        for ordem,(nome,tipos) in enumerate(DADOS.items()):
            cat,_=CategoriaOcorrencia.objects.get_or_create(nome=nome,defaults={'ordem':ordem})
            for tipo in tipos:TipoProblema.objects.get_or_create(categoria=cat,nome=tipo)
        self.stdout.write(self.style.SUCCESS('Categorias e tipos de problema carregados.'))
