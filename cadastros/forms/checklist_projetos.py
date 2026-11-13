from django import forms

from cadastros.models import ChecklistProjetoGrupo, ChecklistProjetoItem


class ChecklistProjetoGrupoForm(forms.ModelForm):
    class Meta:
        model = ChecklistProjetoGrupo
        fields = ["tipo", "nome", "slug", "ordem", "ativo"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "cad-input"}),
            "nome": forms.TextInput(attrs={"class": "cad-input"}),
            "slug": forms.TextInput(attrs={"class": "cad-input"}),
            "ordem": forms.NumberInput(attrs={"class": "cad-input", "min": 0}),
            "ativo": forms.CheckboxInput(),
        }


class ChecklistProjetoItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistProjetoItem
        fields = ["grupo", "etapa", "codigo", "entrega_atividade", "ordem", "ativo"]
        widgets = {
            "grupo": forms.Select(attrs={"class": "cad-input"}),
            "etapa": forms.TextInput(attrs={"class": "cad-input"}),
            "codigo": forms.TextInput(attrs={"class": "cad-input"}),
            "entrega_atividade": forms.TextInput(attrs={"class": "cad-input"}),
            "ordem": forms.NumberInput(attrs={"class": "cad-input", "min": 0}),
            "ativo": forms.CheckboxInput(),
        }
