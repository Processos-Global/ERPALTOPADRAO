from django import forms
from django.forms import inlineformset_factory

from cadastros.models import ItemModeloFVS, ModeloFVS


class ModeloFVSForm(forms.ModelForm):
    class Meta:
        model = ModeloFVS
        fields = ["nome", "disciplina", "revisao", "normas_referencias", "descricao", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: FVS - Reboco"}),
            "disciplina": forms.TextInput(attrs={"placeholder": "Ex.: Revestimentos"}),
            "revisao": forms.TextInput(attrs={"placeholder": "R01"}),
            "normas_referencias": forms.Textarea(attrs={"rows": 3, "placeholder": "Ex.: NBR 13749 / NBR 15575"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }


class ItemModeloFVSForm(forms.ModelForm):
    class Meta:
        model = ItemModeloFVS
        fields = ["ordem", "item_verificacao", "metodo_instrumento", "criterio_aceite", "tolerancia", "obrigatorio"]
        widgets = {
            "ordem": forms.NumberInput(attrs={"min": 1}),
            "item_verificacao": forms.TextInput(),
            "metodo_instrumento": forms.TextInput(),
            "criterio_aceite": forms.Textarea(attrs={"rows": 2}),
            "tolerancia": forms.Textarea(attrs={"rows": 2}),
        }


ItemModeloFVSFormSet = inlineformset_factory(
    ModeloFVS,
    ItemModeloFVS,
    form=ItemModeloFVSForm,
    extra=0,
    can_delete=True,
)
