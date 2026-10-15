from django import forms
from django.contrib.auth import get_user_model
from .models import *
from obras.models import Obra, AmbienteFichaTecnica
from .validators import validar_anexo

class StyledFormMixin:
    def style(self):
        for f in self.fields.values():
            f.widget.attrs.setdefault('class','sa-field')

class ClienteForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=Cliente
        fields=['nome','documento','email','telefone','usuario','ativo','portal_habilitado']
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.style()
        from cadastros.models.pos_obra import usuarios_para_portal
        from django.db.models import Q
        self.fields['usuario'].queryset = usuarios_para_portal().filter(
            Q(is_active=True) | Q(pk=self.instance.usuario_id)).order_by('first_name', 'username')
        self.fields['usuario'].help_text = 'Selecione uma conta exclusiva do cliente. Contas internas não podem ser vinculadas.'

    def clean_usuario(self):
        usuario = self.cleaned_data.get('usuario')
        if usuario and not usuario.is_active and usuario.pk != self.instance.usuario_id:
            raise forms.ValidationError('Selecione uma conta ativa para o cliente.')
        return usuario

class EmpreendimentoForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=EmpreendimentoPosObra
        fields=['obra','nome_historico','codigo_historico','endereco_historico','historica','data_entrega']
        widgets={'data_entrega':forms.DateInput(format='%Y-%m-%d', attrs={'type':'date'})}
    def __init__(self,*a,**kw): super().__init__(*a,**kw);self.style()

class VinculoForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=VinculoCliente
        fields=['cliente','empreendimento','papel','ativo']
    def __init__(self,*a,**kw): super().__init__(*a,**kw);self.style()

class CategoriaForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=CategoriaOcorrencia;fields=['nome','ordem','ativa']
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.style()

class TipoProblemaForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=TipoProblema;fields=['categoria','nome','ativo']
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.style()

class ChamadoForm(StyledFormMixin, forms.ModelForm):
    arquivo = forms.FileField(label='Foto ou documento', required=False, validators=[validar_anexo],
                              help_text='Opcional. PDF, imagem ou Word, até 15 MB.')

    class Meta:
        model = Chamado
        fields = ['empreendimento', 'cliente', 'tipo_problema', 'ambiente_padrao',
                  'ambiente_ficha', 'ambiente_detalhe', 'descricao']
        labels = {'empreendimento': 'Imóvel', 'tipo_problema': 'Tipo de ocorrência',
                  'ambiente_ficha': 'Ambiente da ficha técnica', 'ambiente_detalhe': 'Complemento do ambiente',
                  'descricao': 'Descrição do problema'}
        widgets = {'descricao': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, cliente_portal=None, **kwargs):
        super().__init__(*args, **kwargs)
        imoveis = EmpreendimentoPosObra.objects.filter(liberada=True).select_related('obra')
        if cliente_portal:
            imoveis = imoveis.filter(vinculos__cliente=cliente_portal, vinculos__ativo=True)
            self.fields['cliente'].queryset = Cliente.objects.filter(pk=cliente_portal.pk, ativo=True)
            self.fields['cliente'].initial = cliente_portal.pk
            self.fields['cliente'].widget = forms.HiddenInput()
        else:
            self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True).order_by('nome')
        self.fields['empreendimento'].queryset = imoveis.distinct()
        self.fields['tipo_problema'].queryset = TipoProblema.objects.filter(
            ativo=True, categoria__ativa=True).select_related('categoria')
        self.fields['ambiente_ficha'].queryset = AmbienteFichaTecnica.objects.none()
        raw = self.data.get(self.add_prefix('empreendimento')) if self.is_bound else self.initial.get('empreendimento')
        try:
            empreendimento = imoveis.filter(pk=raw).first() if raw else None
        except (TypeError, ValueError):
            empreendimento = None
        if empreendimento and not empreendimento.historica:
            self.fields['ambiente_ficha'].queryset = AmbienteFichaTecnica.objects.filter(
                ativo=True, pavimento__ficha__obra_id=empreendimento.obra_id).select_related('pavimento__ficha')
        self.fields['ambiente_padrao'].widget = forms.Select(choices=[('', 'Selecione')] + [
            (x, x) for x in ['Sala', 'Quarto', 'Cozinha', 'Banheiro', 'Piscina', 'Área externa', 'Outro']])
        self.style()

    def clean(self):
        d = super().clean()
        e, c = d.get('empreendimento'), d.get('cliente')
        if e and c and not VinculoCliente.objects.filter(cliente=c, empreendimento=e, ativo=True, cliente__ativo=True).exists():
            self.add_error('cliente', 'Cliente não vinculado ao imóvel.')
        if e:
            if e.historica:
                if not d.get('ambiente_padrao'):
                    self.add_error('ambiente_padrao', 'Selecione o ambiente do imóvel.')
                d['ambiente_ficha'] = None
            else:
                d['ambiente_padrao'] = ''
                if not d.get('ambiente_ficha'):
                    self.add_error('ambiente_ficha', 'Selecione um ambiente da ficha técnica desta obra.')
        return d

class AtendimentoForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=Chamado
        fields=['status','prioridade','responsavel','garantia','triagem','diagnostico','data_vistoria','materiais_observacao','execucao','data_execucao','conclusao']
        widgets={'data_vistoria':forms.DateInput(format='%Y-%m-%d', attrs={'type':'date'}),'data_execucao':forms.DateInput(format='%Y-%m-%d', attrs={'type':'date'}),'triagem':forms.Textarea(attrs={'rows':3}),'diagnostico':forms.Textarea(attrs={'rows':4}),'materiais_observacao':forms.Textarea(attrs={'rows':3}),'execucao':forms.Textarea(attrs={'rows':4}),'conclusao':forms.Textarea(attrs={'rows':3})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsavel'].queryset = get_user_model().objects.filter(
            is_active=True, cliente_saari__isnull=True).order_by('first_name', 'username')
        self.style()

class MaterialForm(StyledFormMixin, forms.Form):
    from cadastros.models import Material
    material = forms.ModelChoiceField(
        queryset=Material.objects.filter(ativo=True).select_related('unidade').order_by('nome'),
        label='Material do catálogo SAARI', empty_label='Selecione o material'
    )
    previsto = forms.DecimalField(label='Quantidade necessária', min_value=0.001, max_digits=12, decimal_places=3)
    utilizado = forms.DecimalField(label='Quantidade utilizada', min_value=0, max_digits=12, decimal_places=3, required=False, initial=0)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style()


class PesquisaForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=PesquisaSatisfacao;fields=['atendimento','prazo','qualidade','resolvido','comentario']
        widgets={'comentario':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.style()
        for x in ('atendimento','prazo','qualidade'):self.fields[x].widget=forms.Select(choices=[('', 'Selecione'), (5, 'Sim'), (1, 'Não')])
        self.fields['resolvido'].widget=forms.Select(choices=[('', 'Selecione'), ('SIM','Sim'), ('NAO','Não')])

class ObraHistoricaForm(StyledFormMixin,forms.ModelForm):
    class Meta:
        model=EmpreendimentoPosObra
        fields=['nome_historico','codigo_historico','endereco_historico','data_entrega']
        widgets={'data_entrega':forms.DateInput(format='%Y-%m-%d', attrs={'type':'date'})}
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.style()

class MaterialQuantidadeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialOS
        fields = ['previsto', 'utilizado']
        labels = {'previsto': 'Quantidade necessária', 'utilizado': 'Quantidade utilizada'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['previsto'].min_value = 0.001
        self.fields['utilizado'].min_value = 0
        self.style()
    def clean_previsto(self):
        from decimal import Decimal
        value = self.cleaned_data['previsto']
        if value < Decimal('0.001'):
            raise forms.ValidationError('Informe quantidade maior que zero.')
        return value
    def clean_utilizado(self):
        value = self.cleaned_data['utilizado']
        if value < 0:
            raise forms.ValidationError('A quantidade utilizada não pode ser negativa.')
        return value

class AnexoForm(StyledFormMixin, forms.Form):
    arquivo = forms.FileField(validators=[validar_anexo], label='Arquivo')
    etapa = forms.ChoiceField(choices=AnexoChamado._meta.get_field('etapa').choices)
    publico = forms.BooleanField(required=False, label='Disponível para o cliente')
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style()
