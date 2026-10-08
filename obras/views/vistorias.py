from django.contrib import messages
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from obras.models import VistoriaHistorico, VistoriaItem
from planejamento.models import ImportacaoCronograma, RegistroCronograma
from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao

# O filtro é executado no banco, antes de percorrer os snapshots semanais.
# As variantes abaixo preservam textos antigos, antes da normalização do CSV.
_DISCIPLINAS = (
    'CHECKLIST HABITE-SE', 'CHECKLIST PRE HABITE-SE',
    'CHECKLIST PRÉ HABITE-SE', 'POS HABITE-SE', 'PÓS HABITE-SE',
)
_PRE = {'CHECKLIST HABITE-SE', 'CHECKLIST PRE HABITE-SE', 'CHECKLIST PRÉ HABITE-SE'}


def _importacao_id():
    return (ImportacaoCronograma.objects.filter(
        ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA
    ).order_by('-id').values_list('id', flat=True).first())


def _registros(importacao_id):
    return (RegistroCronograma.objects.filter(
        importacao_id=importacao_id, obra__ativa=True,
        atividade_planejamento__isnull=False, atividade_planejamento__ativa=True,
        disciplina__in=_DISCIPLINAS,
    ).order_by('-semana', '-id').values(
        'atividade_planejamento_id', 'obra_id', 'obra__nome', 'disciplina',
        'local_tarefa', 'nome_tarefa', 'atividade_planejamento__nome_tarefa',
    ))


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def vistorias_lista(request):
    importacao_id = _importacao_id()
    try:
        obra_solicitada = int(request.GET.get('obra') or 0)
    except (ValueError, TypeError):
        obra_solicitada = 0

    # Uma consulta leve de IDs/nomes para construir as abas, sem carregar os snapshots.
    obras = []
    itens = []
    if importacao_id:
        abas = (RegistroCronograma.objects.filter(
            importacao_id=importacao_id, obra__ativa=True,
            atividade_planejamento__isnull=False, atividade_planejamento__ativa=True,
            disciplina__in=_DISCIPLINAS,
        ).order_by('obra__nome', 'obra_id').values('obra_id', 'obra__nome').distinct())
        obras = [{'pk': r['obra_id'], 'nome': r['obra__nome']} for r in abas]
        ids = {o['pk'] for o in obras}
        obra_id = obra_solicitada if obra_solicitada in ids else (obras[0]['pk'] if obras else None)
        if obra_id:
            vistos = set()
            # Restringir snapshots à obra selecionada.
            for r in _registros(importacao_id).filter(obra_id=obra_id).iterator(chunk_size=1000):
                aid = r['atividade_planejamento_id']
                if aid in vistos:
                    continue
                vistos.add(aid)
                itens.append({
                    'atividade_id': aid, 'obra_id': r['obra_id'],
                    'tipo': 'PRE' if r['disciplina'] in _PRE else 'POS',
                    'local': r['local_tarefa'] or 'Sem local informado',
                    'nome': r['nome_tarefa'] or r['atividade_planejamento__nome_tarefa'],
                })
    else:
        obra_id = None

    estados = {v.atividade_id: v for v in VistoriaItem.objects.filter(
        atividade_id__in=[i['atividade_id'] for i in itens]
    ).only('atividade_id', 'status', 'atualizado_em')}
    grupos = []
    for tipo, rotulo in (('PRE', 'Pré Habite-se'), ('POS', 'Pós Habite-se')):
        rows = []
        for item in itens:
            if item['tipo'] != tipo:
                continue
            estado = estados.get(item['atividade_id'])
            rows.append({**item, 'status': estado.status if estado else 'NAO_FEITO',
                         'atualizado_em': estado.atualizado_em if estado else None})
        grupos.append({'tipo': tipo, 'titulo': rotulo, 'linhas': rows,
                       'feitos': sum(r['status'] == 'FEITO' for r in rows)})
    return render(request, 'obras/vistorias/lista.html', {
        'obras': obras, 'obra_id': obra_id, 'grupos': grupos,
    })


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def vistoria_alterar(request, atividade_id):
    status = request.POST.get('status')
    if status not in VistoriaItem.Status.values:
        raise Http404('Status inválido')
    importacao_id = _importacao_id()
    if not importacao_id:
        raise Http404('Nenhum cronograma ativo')
    # Consulta EXISTS: verifica uma única atividade, sem reler o cronograma inteiro.
    registro = (RegistroCronograma.objects.filter(
        importacao_id=importacao_id, atividade_planejamento_id=atividade_id,
        atividade_planejamento__ativa=True, obra__ativa=True,
        disciplina__in=_DISCIPLINAS,
    ).values('obra_id').first())
    if not registro:
        raise Http404('Atividade indisponível no cronograma ativo')

    with transaction.atomic():
        item, _ = VistoriaItem.objects.select_for_update().get_or_create(
            atividade_id=atividade_id, defaults={'status': 'NAO_FEITO'})
        anterior = item.status
        if anterior != status:
            item.status = status
            item.atualizado_por = request.user
            item.save(update_fields=['status', 'atualizado_por', 'atualizado_em'])
            VistoriaHistorico.objects.create(
                item=item, status_anterior=anterior, status_novo=status,
                usuario=request.user)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'status': item.status,
                             'atualizado_em': timezone.localtime(item.atualizado_em).strftime('%d/%m/%Y %H:%M')})
    messages.success(request, 'Vistoria atualizada.')
    return redirect(f"/obras/vistorias/?obra={registro['obra_id']}")
