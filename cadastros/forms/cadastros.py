from django import forms

from cadastros.models import Fornecedor, MaoObra, Material


class FormBaseMixin:
    def aplicar_classes(self):
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} cad-input".strip()


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
