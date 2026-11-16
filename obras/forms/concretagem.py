from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth import get_user_model

from cadastros.models import Fornecedor
from obras.models import Concretagem, LocalUsoObra, Obra


class ConcretagemForm(forms.ModelForm):
    salvar_endereco = forms.BooleanField(required=False, label="Salvar este endereço para próximas solicitações")
    nome_endereco = forms.CharField(required=False, max_length=160, label="Nome do endereço salvo")

    class Meta:
        model = Concretagem
        fields = [
            "obra", "engenheiro", "concreteira", "data_programada", "horario_programado",
            "fck_projeto", "slump", "slump_tolerancia", "agregado", "volume_solicitado", "com_bomba",
            "endereco_entrega", "link_maps_entrega", "razao_social_empreendimento", "observacoes",
        ]
        widgets = {
            "data_programada": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "horario_programado": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "fck_projeto": forms.NumberInput(attrs={"step": "0.5", "min": "0", "placeholder": "Ex.: 30"}),
            "volume_solicitado": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "m³"}),
            "slump": forms.TextInput(attrs={"placeholder": "Ex.: 10"}),
            "slump_tolerancia": forms.TextInput(attrs={"placeholder": "Ex.: 2"}),
            "agregado": forms.TextInput(attrs={"placeholder": "Ex.: Brita 0 e 1"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["obra"].queryset = Obra.objects.filter(ativa=True).order_by("nome")
        self.fields["concreteira"].queryset = Fornecedor.objects.filter(ativo=True).order_by("nome")
        self.fields["concreteira"].label_from_instance = lambda f: f.nome_fantasia or f.nome
        user_model = get_user_model()
        self.fields["engenheiro"].queryset = user_model.objects.filter(is_active=True).order_by("first_name", "username")
        self.fields["engenheiro"].label_from_instance = lambda u: u.get_full_name() or u.username
        # Concreteira e engenheiro são obrigatórios: a solicitação vai para a
        # concreteira e o aceite é comunicado por e-mail ao engenheiro.
        self.fields["concreteira"].required = True
        self.fields["engenheiro"].required = True
        if self.instance.pk:
            # A obra não muda depois de criada: itens e locais pertencem a ela.
            self.fields["obra"].disabled = True

    def clean(self):
        dados = super().clean()
        if dados.get("salvar_endereco") and not dados.get("endereco_entrega"):
            self.add_error("endereco_entrega", "Informe o endereço para salvá-lo.")
        return dados

    def save(self, commit=True):
        conc = super().save(commit=False)
        if not conc.com_bomba:
            conc.nome_bombista = ""
        if commit:
            conc.save()
        return conc


def extrair_itens(post, obra):
    """Lê as linhas dinâmicas de itens planejados (item_local/item_descricao/item_volume).

    Retorna (itens, erros). Linhas totalmente vazias são ignoradas; o local
    precisa pertencer à obra da concretagem.
    """
    locais_ids = post.getlist("item_local")
    descricoes = post.getlist("item_descricao")
    volumes = post.getlist("item_volume")
    total = max(len(locais_ids), len(descricoes), len(volumes))
    locais = {
        str(l.pk): l for l in LocalUsoObra.objects.filter(obra=obra, ativo=True)
    } if obra else {}
    itens, erros = [], []
    for i in range(total):
        local_id = (locais_ids[i] if i < len(locais_ids) else "").strip()
        descricao = (descricoes[i] if i < len(descricoes) else "").strip()[:300]
        volume_txt = (volumes[i] if i < len(volumes) else "").strip().replace(",", ".")
        if not (local_id or descricao or volume_txt):
            continue
        linha = i + 1
        local = None
        if local_id:
            local = locais.get(local_id)
            if local is None:
                erros.append(f"Item {linha}: local inválido para esta obra.")
                continue
        if not local:
            erros.append(f"Item {linha}: escolha o local de uso (cadastre um novo pelo botão “+ Adicionar local”).")
            continue
        try:
            volume = Decimal(volume_txt)
        except (InvalidOperation, ValueError):
            erros.append(f"Item {linha}: volume inválido.")
            continue
        if volume <= 0:
            erros.append(f"Item {linha}: o volume deve ser maior que zero.")
            continue
        itens.append({"local": local, "descricao": descricao, "volume_previsto": volume.quantize(Decimal("0.01"))})
    return itens, erros


class LocalUsoForm(forms.ModelForm):
    class Meta:
        model = LocalUsoObra
        fields = ["nome", "tipo", "bloco", "pavimento", "volume_estimado", "ordem"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Laje 2º pavimento, Piscina"}),
            "volume_estimado": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, obra=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.obra = obra or getattr(self.instance, "obra", None)

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        qs = LocalUsoObra.objects.filter(obra=self.obra, nome__iexact=nome)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe um local com esse nome nesta obra.")
        return nome


# ---------------------------------------------------------------------------
# Execução em campo, moldagem e laudos
# ---------------------------------------------------------------------------
from obras.models import (  # noqa: E402
    CaminhaoConcretagem, FichaMoldagem, LaudoConcretagem, SerieMoldagem, SobraConcreto, UtilizacaoConcreto,
)

_HORA = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
_M3 = forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"})


class CaminhaoForm(forms.ModelForm):
    class Meta:
        model = CaminhaoConcretagem
        fields = [
            "placa", "numero_lacre", "numero_nota_fiscal", "fck_nota", "volume_entregue",
            "horario_chegada", "inicio_descarga", "termino_descarga", "cps_moldados", "observacoes",
        ]
        widgets = {
            "volume_entregue": _M3,
            "fck_nota": forms.NumberInput(attrs={"step": "0.5", "min": "0"}),
            "horario_chegada": _HORA, "inicio_descarga": _HORA, "termino_descarga": _HORA,
            "cps_moldados": forms.NumberInput(attrs={"min": "0"}),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        dados = super().clean()
        ini, fim = dados.get("inicio_descarga"), dados.get("termino_descarga")
        if ini and fim and fim < ini:
            self.add_error("termino_descarga", "O término não pode ser antes do início da descarga.")
        return dados


class SerieMoldagemForm(forms.ModelForm):
    class Meta:
        model = SerieMoldagem
        fields = [
            "inicio_mistura", "hora_moldagem", "abatimento_medido", "slump_flow", "slump_flow_tolerancia",
            "concreto_aplicado_m3", "local_aplicacao", "junta", "pavimento", "torre", "identificacao_amostra",
        ]
        widgets = {
            "inicio_mistura": _HORA, "hora_moldagem": _HORA, "concreto_aplicado_m3": _M3,
            "identificacao_amostra": forms.Textarea(attrs={"rows": 2}),
        }


class FichaMoldagemForm(forms.ModelForm):
    class Meta:
        model = FichaMoldagem
        exclude = ["concretagem"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora_entrada": _HORA, "hora_saida": _HORA,
        }


class UtilizacaoForm(forms.ModelForm):
    class Meta:
        model = UtilizacaoConcreto
        fields = ["caminhao", "local", "descricao", "volume_utilizado"]
        widgets = {"volume_utilizado": _M3}

    def __init__(self, *args, conc=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["caminhao"].queryset = conc.caminhoes.filter(ativo=True) if conc else CaminhaoConcretagem.objects.none()
        self.fields["local"].queryset = LocalUsoObra.objects.filter(obra=conc.obra, ativo=True) if conc else LocalUsoObra.objects.none()
        self.fields["local"].required = True


class SobraForm(forms.ModelForm):
    class Meta:
        model = SobraConcreto
        fields = ["caminhao", "volume_sobra", "destino", "obra_destino", "local_destino", "descricao_destino"]
        widgets = {"volume_sobra": _M3}

    def __init__(self, *args, conc=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["caminhao"].queryset = conc.caminhoes.filter(ativo=True) if conc else CaminhaoConcretagem.objects.none()
        self.fields["obra_destino"].queryset = Obra.objects.filter(ativa=True).exclude(pk=conc.obra_id if conc else None).order_by("nome")
        self.fields["local_destino"].queryset = LocalUsoObra.objects.filter(obra=conc.obra, ativo=True) if conc else LocalUsoObra.objects.none()


class LaudoForm(forms.Form):
    idade_dias = forms.TypedChoiceField(choices=LaudoConcretagem.Idade.choices, coerce=int, label="Idade")
    resistencia_mpa = forms.DecimalField(max_digits=6, decimal_places=1, min_value=Decimal("0.1"), label="Resistência (MPa)")
    enviado_por_nome = forms.CharField(max_length=200, required=False, label="Quem enviou os CPs")
    observacao = forms.CharField(max_length=300, required=False, label="Observação")
    arquivo = forms.FileField(required=False, label="Laudo (PDF ou foto)")
