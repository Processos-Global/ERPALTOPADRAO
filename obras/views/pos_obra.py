from django.shortcuts import render,redirect,get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from obras.models import Obra
from cadastros.models.pos_obra import EmpreendimentoPosObra
from pos_obra.access import acesso_interno
@login_required
def liberacoes(request):
    if not acesso_interno(request.user):raise PermissionDenied
    obras=Obra.objects.filter(status='CONCLUIDA').order_by('nome')[:200]
    return render(request,'obras/pos_obra_liberacoes.html',{'obras':obras})
@login_required
@require_POST
def liberar(request,obra_id):
    if not acesso_interno(request.user):raise PermissionDenied
    obra=get_object_or_404(Obra,pk=obra_id,status='CONCLUIDA')
    e,_=EmpreendimentoPosObra.objects.get_or_create(obra=obra,defaults={'data_entrega':obra.data_termino_real})
    if not e.liberada:
        e.liberada=True;e.liberado_por=request.user;e.liberado_em=timezone.now();e.save(update_fields=['liberada','liberado_por','liberado_em'])
    return redirect('obras:pos_obra_liberacoes')
