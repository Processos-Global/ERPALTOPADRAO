from django import forms

from obras.models import Obra
from cadastros.models import ChecklistProjetoGrupo
from projetos.models import AlteracaoProjeto


class ObraProjetoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        codigo = (getattr(obj, "codigo", "") or "").strip()
        nome = (getattr(obj, "nome", "") or "").strip()

        # O nome da obra já é a identificação amigável exibida ao usuário.
        # Não concatenamos código + nome para evitar rótulos duplicados,
        # como "QL10-CJ06-C17 · QL 10 CJ 06 CASA 17".
        return nome or codigo or str(obj)


class AlteracaoProjetoForm(forms.ModelForm):
    obra = ObraProjetoChoiceField(
        queryset=Obra.objects.none(),
        widget=forms.Select(attrs={"class": "proj-control"}),
        label="Obra",
    )

    class Meta:
        model = AlteracaoProjeto
        fields = ["obra", "disciplina", "descricao", "arquivo"]
        widgets = {
            "descricao": forms.Textarea(attrs={
                "class": "proj-control",
                "rows": 3,
                "placeholder": "Descreva objetivamente o que foi alterado no projeto.",
            }),
            "arquivo": forms.ClearableFileInput(attrs={"class": "proj-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["disciplina"].queryset = ChecklistProjetoGrupo.objects.filter(tipo=ChecklistProjetoGrupo.TIPO_COMPATIBILIZACAO, ativo=True).order_by("ordem", "nome")
        self.fields["disciplina"].required = True
        self.fields["disciplina"].label = "Disciplina alterada"
        self.fields["disciplina"].label_from_instance = lambda obj: obj.nome
        self.fields["obra"].queryset = Obra.objects.filter(ativa=True).order_by("codigo", "nome")
