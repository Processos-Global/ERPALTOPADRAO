from django import forms
from django.forms import modelformset_factory

from cadastros.models import ModeloFVS
from obras.models import AmbienteFichaTecnica, FVS, FVSItem, Obra


class FVSCriacaoForm(forms.ModelForm):
    ambientes = forms.ModelMultipleChoiceField(
        queryset=AmbienteFichaTecnica.objects.none(),
        required=True,
        widget=forms.SelectMultiple(attrs={"size": 8, "class": "fvs-hidden-select"}),
        label="Ambientes",
    )

    class Meta:
        model = FVS
        fields = [
            "obra", "modelo_origem", "ambientes", "pavimento_etapa",
            "empresa_executora", "responsavel_execucao", "responsavel_inspecao", "projeto_versao",
        ]
        widgets = {
            "obra": forms.Select(),
            "modelo_origem": forms.Select(),
            "pavimento_etapa": forms.TextInput(attrs={"placeholder": "Opcional; pode ser inferido dos ambientes"}),
            "empresa_executora": forms.TextInput(),
            "responsavel_execucao": forms.TextInput(),
            "responsavel_inspecao": forms.TextInput(),
            "projeto_versao": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["obra"].queryset = Obra.objects.filter(ativa=True).order_by("nome")
        self.fields["modelo_origem"].queryset = ModeloFVS.objects.filter(ativo=True).order_by("nome")
        obra_id = None
        if self.data.get("obra"):
            obra_id = self.data.get("obra")
        elif self.instance and self.instance.pk:
            obra_id = self.instance.obra_id
        if obra_id:
            self.fields["ambientes"].queryset = AmbienteFichaTecnica.objects.filter(pavimento__ficha__obra_id=obra_id, ativo=True).select_related("pavimento", "tipo_ambiente").order_by("pavimento__ordem", "ordem", "identificacao")

    def clean(self):
        cleaned = super().clean()
        obra = cleaned.get("obra")
        ambientes = cleaned.get("ambientes")
        if obra and ambientes:
            invalidos = [a for a in ambientes if a.pavimento.ficha.obra_id != obra.pk]
            if invalidos:
                self.add_error("ambientes", "Selecione somente ambientes pertencentes à obra escolhida.")
        return cleaned


class FVSResumoForm(forms.ModelForm):
    class Meta:
        model = FVS
        fields = ["parecer", "observacao_final"]
        widgets = {"observacao_final": forms.Textarea(attrs={"rows": 4})}


class FVSItemForm(forms.ModelForm):
    resultado = forms.ChoiceField(
        choices=FVSItem.Resultado.choices,
        required=False,
        widget=forms.RadioSelect,
        label="Resultado",
    )

    class Meta:
        model = FVSItem
        fields = ["resultado", "data_verificacao", "observacao"]
        widgets = {
            "data_verificacao": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 1, "placeholder": "Observação ou ação corretiva"}),
        }


FVSItemFormSet = modelformset_factory(FVSItem, form=FVSItemForm, extra=0)


class FVSDecisaoForm(forms.Form):
    decisao = forms.ChoiceField(choices=[("APROVAR", "Aprovar"), ("DEVOLVER", "Devolver para correção")])
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Informe o motivo ao devolver a ficha"}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decisao") == "DEVOLVER" and not (cleaned.get("observacao") or "").strip():
            self.add_error("observacao", "Informe o motivo da devolução.")
        return cleaned
