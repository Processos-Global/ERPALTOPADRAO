from django import forms
from django.contrib import messages
from django.shortcuts import render, redirect
from cadastros.models import DadosEmpresa
from cadastros.views.cadastros import cadastros_permissao_required, _permissoes_contexto

class DadosEmpresaForm(forms.ModelForm):
    class Meta:
        model = DadosEmpresa
        exclude = ('atualizado_em',)
        widgets = {'logo': forms.ClearableFileInput(attrs={'accept':'image/*'})}

@cadastros_permissao_required('visualizar')
def empresa(request):
    empresa = DadosEmpresa.atual()
    pode_editar = _permissoes_contexto(request.user)['cad_pode_administrar']
    if request.method == 'POST' and not pode_editar:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Somente administradores de Cadastros podem alterar os dados da empresa.')
    form = DadosEmpresaForm(request.POST or None, request.FILES or None, instance=empresa)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Dados institucionais atualizados com sucesso.')
        return redirect('cadastros:empresa')
    return render(request, 'cadastros/empresa.html', {'form':form,'pode_editar':pode_editar,**_permissoes_contexto(request.user)})
