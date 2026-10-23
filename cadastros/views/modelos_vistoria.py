from django.contrib import messages
from django.db import transaction
from django.forms import ModelForm, inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from cadastros.models import ModeloVistoria, CampoModeloVistoria
from cadastros.views.cadastros import cadastros_permissao_required, _permissoes_contexto


class ModeloForm(ModelForm):
    class Meta:
        model = ModeloVistoria
        fields = ('nome', 'descricao', 'versao', 'ativo')


class CampoForm(ModelForm):
    class Meta:
        model = CampoModeloVistoria
        fields = ('secao', 'chave', 'titulo', 'tipo', 'opcoes', 'obrigatorio', 'ordem')


CampoSet = inlineformset_factory(ModeloVistoria, CampoModeloVistoria, form=CampoForm, extra=2, can_delete=True)


@cadastros_permissao_required('visualizar')
def modelos_vistoria_lista(request):
    return render(request, 'cadastros/vistorias/lista.html', {
        'modelos': ModeloVistoria.objects.prefetch_related('campos'),
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required('editar')
def modelo_vistoria_editar(request, pk=None):
    modelo = get_object_or_404(ModeloVistoria, pk=pk) if pk else None
    form = ModeloForm(request.POST or None, instance=modelo)
    formset = CampoSet(request.POST or None, instance=modelo, prefix='campos')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            novo = form.save()
            formset.instance = novo
            formset.save()
        messages.success(request, 'Modelo de vistoria salvo.')
        return redirect('cadastros:modelos_vistoria_lista')
    return render(request, 'cadastros/vistorias/form.html', {
        'form': form, 'formset': formset, 'modelo': modelo,
        **_permissoes_contexto(request.user),
    })
