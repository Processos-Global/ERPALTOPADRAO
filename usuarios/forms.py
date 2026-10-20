from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from usuarios.models import PerfilUsuario, PermissaoModulo
from cadastros.models.pos_obra import Cliente


class UsuarioSistemaForm(forms.ModelForm):
    first_name = forms.CharField(label="Nome", max_length=150, required=True)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    email = forms.EmailField(label="E-mail", required=False)
    tipo_acesso = forms.ChoiceField(label="Tipo de acesso", choices=[("INTERNO", "Colaborador SAARI"), ("CLIENTE", "Cliente — Portal Pós-Obra")])
    cliente_vinculado = forms.ModelChoiceField(label="Cliente cadastrado", queryset=Cliente.objects.none(), required=False, empty_label="Selecione um cliente")
    cargo = forms.ChoiceField(label="Cargo/setor", choices=PerfilUsuario.Cargo.choices)
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
            if not cliente:
                self.add_error("cliente_vinculado", "Selecione primeiro o cliente cadastrado no Pós-Obra.")
            if self.instance.pk and (self.instance.is_staff or self.instance.is_superuser or PermissaoModulo.objects.filter(usuario=self.instance, ativo=True).exists()):
                self.add_error("tipo_acesso", "Esta conta possui privilégios internos. Remova-os antes de vinculá-la a um cliente.")
            if vinculado and cliente and vinculado.pk != cliente.pk:
                self.add_error("cliente_vinculado", "Este usuário já pertence a outro cliente.")
        elif vinculado:
            self.add_error("tipo_acesso", "Para preservar a segurança e o histórico, não é permitido converter uma conta de cliente em interna. Crie outro usuário.")
        senha = cleaned.get("senha") or ""
        confirmar = cleaned.get("confirmar_senha") or ""
        if not self.instance.pk and not senha:
            self.add_error("senha", "Informe uma senha para o novo usuário.")
        if senha and senha != confirmar:
            self.add_error("confirmar_senha", "As senhas informadas não coincidem.")
        if senha:
            try:
                validate_password(senha, self.instance if self.instance and self.instance.pk else None)
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
        usuario.is_active = bool(self.cleaned_data.get("ativo"))
        if self.cleaned_data.get("tipo_acesso") == "CLIENTE":
            usuario.is_staff = False
            usuario.is_superuser = False
        senha = self.cleaned_data.get("senha") or ""
        if senha:
            usuario.set_password(senha)
        if commit:
            usuario.save()
            perfil, _ = PerfilUsuario.objects.get_or_create(usuario=usuario)
            tipo_cliente = self.cleaned_data.get("tipo_acesso") == "CLIENTE"
            perfil.cargo = PerfilUsuario.Cargo.OUTRO if tipo_cliente else (self.cleaned_data.get("cargo") or PerfilUsuario.Cargo.OUTRO)
            perfil.telefone = self.cleaned_data.get("telefone") or ""
            perfil.ativo = usuario.is_active
            perfil.save()
            if tipo_cliente:
                cliente = self.cleaned_data["cliente_vinculado"]
                cliente.usuario = usuario
                cliente.portal_habilitado = True
                cliente.save(update_fields=["usuario", "portal_habilitado"])
        return usuario
