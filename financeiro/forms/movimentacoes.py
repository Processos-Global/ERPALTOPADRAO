from django import forms

from financeiro.models import MovimentacaoBancaria
from .cadastros import ERPModelForm


class AjusteBancarioForm(ERPModelForm):
    class Meta:
        model = MovimentacaoBancaria
        fields = ("conta_bancaria", "tipo", "data", "valor", "descricao", "referencia_extrato")
        widgets = {"data": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [
            (MovimentacaoBancaria.Tipo.AJUSTE_CREDITO, "Ajuste de crédito"),
            (MovimentacaoBancaria.Tipo.AJUSTE_DEBITO, "Ajuste de débito"),
        ]
