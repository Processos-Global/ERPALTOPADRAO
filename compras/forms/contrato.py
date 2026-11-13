from django import forms
from django.apps import apps
from django.utils import timezone

from compras.models import ContratoCompra, ProcessoCompra


class ContratoCompraForm(forms.ModelForm):
    class Meta:
        model = ContratoCompra
        fields = [
            "processo", "obra", "fornecedor",
            "contratado_razao_social", "contratado_cnpj", "contratado_endereco", "contratado_email",
            "representante_nome", "representante_nacionalidade", "representante_estado_civil",
            "representante_profissao", "representante_cpf", "representante_endereco",
            "modalidade_fornecimento", "objeto_contrato", "area_obra", "descricao_ambientes_objeto",
            "escritorio_arquitetura", "responsavel_supervisao", "prazo_execucao", "multa_atraso",
            "valor_total", "favorecido_nome", "favorecido_documento_tipo", "favorecido_documento",
            "banco", "agencia", "conta", "operacao", "pix",
            "avalista_1_nome", "avalista_1_cpf", "avalista_2_nome", "avalista_2_cpf",
            "cidade_assinatura", "data_contrato", "observacoes_internas",
        ]
        widgets = {
            "objeto_contrato": forms.Textarea(attrs={"rows": 4}),
            "descricao_ambientes_objeto": forms.Textarea(attrs={"rows": 4}),
            "observacoes_internas": forms.Textarea(attrs={"rows": 3}),
            "data_contrato": forms.DateInput(attrs={"type": "date"}),
            "area_obra": forms.NumberInput(attrs={"step": "0.01"}),
            "multa_atraso": forms.NumberInput(attrs={"step": "0.01"}),
            "valor_total": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Fornecedor = apps.get_model("cadastros", "Fornecedor")
        self.fields["fornecedor"].queryset = Fornecedor.objects.all().order_by("nome")
        self.fields["processo"].queryset = ProcessoCompra.objects.select_related("obra").exclude(
            status=ProcessoCompra.Status.CANCELADO
        ).order_by("-criado_em")
        self.fields["processo"].required = False

        if not self.is_bound and not self.instance.pk:
            self.fields["data_contrato"].initial = timezone.localdate()

        labels = {
            "processo": "Processo de compra (opcional)",
            "fornecedor": "Fornecedor / contratado",
            "contratado_razao_social": "Razão social do contratado",
            "contratado_cnpj": "CNPJ do contratado",
            "contratado_endereco": "Endereço do contratado",
            "contratado_email": "E-mail do contratado",
            "representante_nome": "Nome do representante",
            "representante_nacionalidade": "Nacionalidade",
            "representante_estado_civil": "Estado civil",
            "representante_profissao": "Profissão / cargo",
            "representante_cpf": "CPF do representante",
            "representante_endereco": "Endereço do representante",
            "modalidade_fornecimento": "Modalidade / fornecimento",
            "objeto_contrato": "Objeto do contrato",
            "area_obra": "Área aproximada da obra (m²)",
            "descricao_ambientes_objeto": "Descrição dos ambientes / escopo",
            "escritorio_arquitetura": "Escritório de arquitetura",
            "responsavel_supervisao": "Responsável pela supervisão",
            "prazo_execucao": "Prazo de execução",
            "multa_atraso": "Multa diária por atraso",
            "valor_total": "Valor total do contrato",
            "favorecido_nome": "Titular / favorecido",
            "favorecido_documento_tipo": "Tipo de documento",
            "favorecido_documento": "Documento do favorecido",
            "banco": "Banco", "agencia": "Agência", "conta": "Conta",
            "operacao": "Operação", "pix": "PIX",
            "avalista_1_nome": "Avalista 1 - nome", "avalista_1_cpf": "Avalista 1 - CPF",
            "avalista_2_nome": "Avalista 2 - nome", "avalista_2_cpf": "Avalista 2 - CPF",
            "cidade_assinatura": "Cidade de assinatura",
            "data_contrato": "Data do contrato",
            "observacoes_internas": "Observações internas",
        }
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)
            css = "saari-input"
            if isinstance(field.widget, forms.Select):
                css += " saari-select"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        processo = cleaned.get("processo")
        obra = cleaned.get("obra")
        if processo and obra and processo.obra_id != obra.pk:
            self.add_error("processo", "O processo selecionado pertence a outra obra.")
        return cleaned


class DecisaoContratoForm(forms.Form):
    decisao = forms.ChoiceField(choices=(
        ("APROVAR", "Aprovar"),
        ("DEVOLVER", "Devolver para correção"),
        ("REPROVAR", "Reprovar"),
    ))
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decisao") in {"DEVOLVER", "REPROVAR"} and not (cleaned.get("observacao") or "").strip():
            self.add_error("observacao", "Informe o motivo da devolução/reprovação.")
        return cleaned


class ContratoAssinadoForm(forms.ModelForm):
    class Meta:
        model = ContratoCompra
        fields = ["arquivo_assinado"]
        widgets = {"arquivo_assinado": forms.ClearableFileInput(attrs={"accept": ".pdf,.doc,.docx"})}

    def clean_arquivo_assinado(self):
        arquivo = self.cleaned_data.get("arquivo_assinado")
        if not arquivo:
            raise forms.ValidationError("O contrato assinado é obrigatório.")
        return arquivo
