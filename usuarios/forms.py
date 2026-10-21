from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from usuarios.models import PerfilUsuario, PermissaoModulo
from cadastros.models.pos_obra import Cliente, EmpreendimentoPosObra, VinculoCliente


class UsuarioSistemaForm(forms.ModelForm):
    first_name = forms.CharField(label="Nome", max_length=150, required=True)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    email = forms.EmailField(label="E-mail", required=False)
    tipo_acesso = forms.ChoiceField(label="Tipo de acesso", choices=[("INTERNO", "Colaborador SAARI"), ("CLIENTE", "Cliente — Portal Pós-Obra")])
    cliente_vinculado = forms.ModelChoiceField(label="Aproveitar cliente legado (opcional)", queryset=Cliente.objects.none(), required=False, empty_label="Criar novo cliente automaticamente")
    empreendimentos_cliente = forms.ModelMultipleChoiceField(
        label="Imóveis vinculados ao portal", queryset=EmpreendimentoPosObra.objects.none(),
        required=False, widget=forms.CheckboxSelectMultiple(),
        help_text="Pesquise e marque as obras. Desmarcar preserva o histórico e revoga o vínculo de acesso."
    )
    cargo = forms.ChoiceField(label="Cargo/setor", choices=PerfilUsuario.Cargo.choices, required=False)
    telefone = forms.CharField(label="Telefone", max_length=30, required=False)
    ativo = forms.BooleanField(label="Usuário ativo", required=False, initial=True)
    senha = forms.CharField(
        label="Senha",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Obrigatória ao criar. Ao editar, deixe em branco para manter a senha atual.",
    )
    confirmar_senha = forms.CharField(
        label="Confirmar senha",
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )

    cliente_nome = forms.CharField(label="Nome / razão social", max_length=255, required=False)
    cliente_documento = forms.CharField(label="CPF/CNPJ", max_length=20, required=False)
    cliente_email = forms.EmailField(label="E-mail de contato do cliente", required=False)
    cliente_telefone = forms.CharField(label="Telefone do cliente", max_length=40, required=False)
    cliente_ativo = forms.BooleanField(label="Cadastro do cliente ativo", required=False, initial=True)
    portal_habilitado = forms.BooleanField(label="Habilitar portal", required=False, initial=True,
        help_text="O acesso exige também conta ativa, cliente ativo e ao menos uma obra vinculada.")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {"username": "Usuário"}

    def __init__(self, *args, usuario_alvo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_alvo = usuario_alvo or self.instance
        perfil = None
        if self.instance and self.instance.pk:
            perfil = getattr(self.instance, "perfil_erp", None)

        cliente_atual = Cliente.objects.filter(usuario=self.instance).first() if self.instance.pk else None
        self.fields["tipo_acesso"].initial = "CLIENTE" if cliente_atual else "INTERNO"
        self.fields["cliente_vinculado"].queryset = Cliente.objects.filter(usuario__isnull=True) | Cliente.objects.filter(usuario=self.instance.pk) if self.instance.pk else Cliente.objects.filter(usuario__isnull=True)
        self.fields["cliente_vinculado"].initial = cliente_atual
        vinculados = VinculoCliente.objects.filter(cliente=cliente_atual, ativo=True).values_list('empreendimento_id', flat=True) if cliente_atual else []
        self.fields['empreendimentos_cliente'].queryset = EmpreendimentoPosObra.objects.filter(liberada=True) | EmpreendimentoPosObra.objects.filter(pk__in=vinculados)
        self.fields['empreendimentos_cliente'].queryset = self.fields['empreendimentos_cliente'].queryset.distinct().select_related('obra').order_by('nome_historico', 'pk')
        self.fields['empreendimentos_cliente'].initial = list(vinculados)
        self.cliente_atual = cliente_atual
        if cliente_atual:
            for campo in ('nome', 'documento', 'email', 'telefone', 'ativo'):
                self.fields['cliente_' + campo].initial = getattr(cliente_atual, campo)
            self.fields['portal_habilitado'].initial = cliente_atual.portal_habilitado
            self.fields['cliente_vinculado'].disabled = True
        if perfil:
            self.fields["cargo"].initial = perfil.cargo
            self.fields["telefone"].initial = perfil.telefone
        if self.instance and self.instance.pk:
            self.fields["ativo"].initial = self.instance.is_active

        for nome, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "usr-checkbox")
            else:
                field.widget.attrs.setdefault("class", "usr-input")
            if nome == "username":
                field.widget.attrs.setdefault("autocomplete", "off")
            if nome in {"senha", "confirmar_senha"}:
                field.widget.attrs.setdefault("autocomplete", "new-password")

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_acesso")
        cliente = cleaned.get("cliente_vinculado")
        vinculado = Cliente.objects.filter(usuario=self.instance).first() if self.instance.pk else None
        if tipo == "CLIENTE":
            if not cleaned.get('cliente_nome'):
                self.add_error('cliente_nome', 'Informe o nome ou razão social do cliente.')
            from usuarios.services.clientes import normalizar_documento, clientes_com_documento
            documento = normalizar_documento(cleaned.get('cliente_documento'))
            cleaned['cliente_documento'] = documento
            if documento and clientes_com_documento(documento).exclude(pk=(vinculado or cliente).pk if (vinculado or cliente) else None).exists():
                self.add_error('cliente_documento', 'Documento já cadastrado. Selecione o cliente legado explicitamente ou revise a duplicidade.')
            legado_com_obras = cliente and not cliente.usuario_id and cliente.vinculos.filter(ativo=True).exists()
            if cleaned.get('portal_habilitado') and not cleaned.get('empreendimentos_cliente') and not legado_com_obras:
                self.add_error('empreendimentos_cliente', 'Selecione ao menos um imóvel para habilitar o acesso ao portal.')
            if self.instance.pk and (self.instance.is_staff or self.instance.is_superuser or PermissaoModulo.objects.filter(usuario=self.instance, ativo=True).exists()):
                self.add_error("tipo_acesso", "Esta conta possui privilégios internos. Remova-os antes de vinculá-la a um cliente.")
            if vinculado and cliente and vinculado.pk != cliente.pk:
                self.add_error("cliente_vinculado", "Este usuário já pertence a outro cliente.")
        elif vinculado:
            self.add_error("tipo_acesso", "Para preservar a segurança e o histórico, não é permitido converter uma conta de cliente em interna. Crie outro usuário.")
        if tipo == 'INTERNO' and not cleaned.get('cargo'):
            self.add_error('cargo', 'Informe o cargo do colaborador.')
        senha = cleaned.get("senha") or ""
        confirmar = cleaned.get("confirmar_senha") or ""
        if not self.instance.pk and not senha:
            self.add_error("senha", "Informe uma senha para o novo usuário.")
        if senha and senha != confirmar:
            self.add_error("confirmar_senha", "As senhas informadas não coincidem.")
        if senha:
            try:
                validate_password(senha, User(username=cleaned.get('username', ''), first_name=cleaned.get('first_name', ''), last_name=cleaned.get('last_name', ''), email=cleaned.get('email', '')))
            except ValidationError as exc:
                self.add_error("senha", exc)
        return cleaned

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise ValidationError("Informe o usuário.")
        qs = User.objects.filter(username__iexact=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Já existe um usuário com este nome de acesso.")
        return username

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.is_active = bool(self.cleaned_data.get('ativo'))
        senha = self.cleaned_data.get('senha') or ''
        if senha:
            usuario.set_password(senha)
        if not commit:
            return usuario
        from usuarios.services.clientes import salvar_usuario_integrado
        usuario = salvar_usuario_integrado(usuario=usuario, dados=self.cleaned_data)
        # A criação por signal pode ter deixado o relacionamento em cache.
        usuario._state.fields_cache.pop('perfil_erp', None)
        return usuario

    def grupos_campos(self):
        grupos = [
            ('acesso', 'Identificação e acesso', ['tipo_acesso','username','first_name','last_name','email','cargo','telefone','ativo','senha','confirmar_senha']),
            ('cliente', 'Dados do cliente', ['cliente_vinculado','cliente_nome','cliente_documento','cliente_email','cliente_telefone','cliente_ativo','portal_habilitado']),
            ('obras', 'Obras e acesso ao portal', ['empreendimentos_cliente']),
        ]
        return [{'codigo': codigo, 'titulo': titulo, 'campos': [self[n] for n in nomes]} for codigo,titulo,nomes in grupos]

    @property
    def clientes_legados(self):
        queryset=self.fields['cliente_vinculado'].queryset
        obras={}
        for cliente_id,obra_id in VinculoCliente.objects.filter(cliente__in=queryset,ativo=True).values_list('cliente_id','empreendimento_id'):
            obras.setdefault(cliente_id,[]).append(obra_id)
        dados=list(queryset.values('id','nome','documento','email','telefone','ativo','portal_habilitado'))
        for cliente in dados:cliente['obras_ativas']=obras.get(cliente['id'],[])
        return dados
