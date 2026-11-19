from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render

from compras.models import RegraPrazoCompra
from compras.services.permissoes import compras_acao_required
from compras.services.sla import criar_regra_prazo
from usuarios.models import AcaoCompra


class RegraPrazoCompraForm(forms.ModelForm):
    class Meta:
        model = RegraPrazoCompra
        fields = ("escopo", "etapa", "tipo_fornecedor", "categoria", "material", "dias",
                  "contagem", "dias_alerta", "vigente_desde", "vigente_ate", "justificativa")
        widgets = {
            "vigente_desde": forms.DateInput(attrs={"type": "date"}),
            "vigente_ate": forms.DateInput(attrs={"type": "date"}),
            "justificativa": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "cp-input"

@compras_acao_required(AcaoCompra.ADMINISTRAR)
def regras_prazo_compra(request):
    form = RegraPrazoCompraForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        criar_regra_prazo(usuario=request.user, **form.cleaned_data)
        messages.success(request, "Nova regra de prazo registrada. As passagens anteriores preservam seus prazos.")
        return redirect("compras:regras_prazo")
    return render(request, "compras/regras_prazo.html", {
        "form": form,
        "regras": RegraPrazoCompra.objects.select_related("categoria", "material", "criado_por")[:100],
    })
