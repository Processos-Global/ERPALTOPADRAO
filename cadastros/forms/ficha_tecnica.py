from django import forms

from cadastros.models import (
    CaracteristicaAmbiente,
    CategoriaGrandeFornecedor,
    OpcaoEspecificacaoGrandeFornecedor,
    TipoAmbiente,
    TipoItemGrandeFornecedor,
    TipoPavimento,
)


class _BaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} cad-input".strip()


class CaracteristicaAmbienteForm(_BaseForm):
    class Meta:
        model = CaracteristicaAmbiente
        fields = ["codigo", "nome", "ativo"]


class TipoPavimentoForm(_BaseForm):
    class Meta:
        model = TipoPavimento
        fields = ["nome", "ordem", "ativo"]


class TipoAmbienteForm(_BaseForm):
    class Meta:
        model = TipoAmbiente
        fields = ["nome", "caracteristica_padrao", "ativo"]


class CategoriaGrandeFornecedorForm(_BaseForm):
    class Meta:
        model = CategoriaGrandeFornecedor
        fields = ["nome", "tipo_preenchimento", "somente_area_molhada", "ordem", "ativo"]


class TipoItemGrandeFornecedorForm(_BaseForm):
    class Meta:
        model = TipoItemGrandeFornecedor
        fields = ["categoria", "nome", "unidade_padrao", "ordem", "ativo"]


class OpcaoEspecificacaoGrandeFornecedorForm(_BaseForm):
    class Meta:
        model = OpcaoEspecificacaoGrandeFornecedor
        fields = ["categoria", "tipo_item", "nome", "ordem", "ativo"]
