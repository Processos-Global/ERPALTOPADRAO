from django import forms

from cadastros.models import Fornecedor, MaoObra, Material, UnidadeMedida


class FormBaseMixin:
    def aplicar_classes(self):
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} cad-input".strip()


class UnidadeMedidaForm(FormBaseMixin, forms.ModelForm):
    class Meta:
        model = UnidadeMedida
        fields = ["sigla", "descricao", "ativo"]
        labels = {
            "sigla": "Sigla",
            "descricao": "Descrição",
            "ativo": "Ativo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()
        self.fields["sigla"].widget.attrs.update({"placeholder": "Ex.: UND, M2, M3, KG, VB"})
        self.fields["descricao"].widget.attrs.update({"placeholder": "Ex.: Unidade, Metro quadrado"})

    def clean_sigla(self):
        sigla = (self.cleaned_data.get("sigla") or "").strip().upper()
        qs = UnidadeMedida.objects.filter(sigla__iexact=sigla)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe uma unidade de medida com esta sigla.")
        return sigla


class MaterialForm(FormBaseMixin, forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            "nome",
            "especificacao",
            "unidade",
            "observacao",
            "ativo",
        ]
        widgets = {
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "nome": "Material",
            "especificacao": "Especificação",
            "unidade": "Unidade",
            "observacao": "Observação",
            "ativo": "Ativo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class FornecedorForm(FormBaseMixin, forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = [
            "nome",
            "nome_fantasia",
            "documento",
            "email",
            "telefone",
            "contato",
            "cidade",
            "estado",
            "avaliacao",
            "observacao",
            "ativo",
        ]
        widgets = {
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()


class MaoObraForm(FormBaseMixin, forms.ModelForm):
    class Meta:
        model = MaoObra
        fields = ["descricao", "categoria", "unidade", "observacao", "ativo"]
        widgets = {
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_classes()
