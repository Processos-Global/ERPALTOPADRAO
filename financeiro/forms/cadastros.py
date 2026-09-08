from django import forms

from financeiro.models import DespesaRecorrente, PlanoFinanceiro


class ERPModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "fin-check")
            else:
                widget.attrs.setdefault("class", "fin-control")


class PlanoFinanceiroForm(ERPModelForm):
    class Meta:
        model = PlanoFinanceiro
        fields = ("codigo", "nome", "tipo", "pai", "ativo")


class DespesaRecorrenteForm(ERPModelForm):
    class Meta:
        model = DespesaRecorrente
        fields = (
            "descricao", "fornecedor", "obra", "plano_financeiro", "valor",
            "dia_vencimento", "inicio", "fim", "ativo", "observacao",
        )
        widgets = {
            "inicio": forms.DateInput(attrs={"type": "date"}),
            "fim": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_dia_vencimento(self):
        dia = self.cleaned_data["dia_vencimento"]
        if not 1 <= dia <= 31:
            raise forms.ValidationError("Informe um dia entre 1 e 31.")
        return dia
