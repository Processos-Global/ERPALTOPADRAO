"""Contexto de leitura da interface; não decide nem grava transições da OS."""
from django.utils import timezone


def etapas_apresentacao(chamado, contexto):
    encerrado=contexto['encerrado']
    specs=[('abertura','Abertura',True,True,'Registrada'),
           ('triagem','Triagem',contexto['concluida_triagem'],True,'Definir responsável e parecer'),
           ('vistoria','Vistoria',contexto['concluida_vistoria'],contexto['libera_vistoria'],'Registrar data e diagnóstico'),
           ('materiais','Materiais',False,contexto['libera_materiais'],'Opcional · planejar materiais'),
           ('execucao','Execução',contexto['concluida_execucao'],contexto['libera_execucao'],'Registrar serviços executados'),
           ('finalizacao','Finalização',chamado.status=='CONCLUIDO',contexto['libera_finalizacao'],'Conferir parecer e aceite'),
           ('satisfacao','Satisfação',contexto['pesquisa'] is not None,True,'Avaliação e tratativas')]
    etapas=[]
    for numero,(codigo,titulo,concluida,liberada,ajuda) in enumerate(specs):
        if concluida:estado='concluida';texto='Concluída'
        elif encerrado:estado='consulta';texto='Consulta'
        elif not liberada:estado='bloqueada';texto='Bloqueada'
        elif codigo=='materiais':estado='opcional';texto='Opcional'
        elif codigo==str(contexto['etapa_pendente'] or 'finalizacao').lower():estado='atual';texto='Próxima ação'
        else:estado='disponivel';texto='Disponível' if codigo!='satisfacao' else 'Após encerramento'
        etapas.append(dict(codigo=codigo,titulo=titulo,numero=f'{numero:02d}',estado=estado,estado_texto=texto,ajuda=ajuda,bloqueada=not liberada and not encerrado))
    return etapas


def proximo_compromisso(agendamentos):
    agora=timezone.now()
    return next((a for a in agendamentos if a.fim>=agora and a.situacao in ('PROPOSTO','CONFIRMADO','REAGENDAMENTO')),None)
