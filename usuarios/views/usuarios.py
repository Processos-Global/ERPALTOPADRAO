from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from usuarios.forms import UsuarioSistemaForm
from usuarios.models import ModuloSistema, NivelPermissao, PerfilUsuario, PermissaoModulo
from usuarios.services import (
    obter_configuracao_modulos_usuario,
    salvar_configuracao_modulos_usuario,
)


def _pode_gerenciar_usuarios(usuario):
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return PermissaoModulo.objects.filter(
        usuario=usuario,
        modulo=ModuloSistema.USUARIOS,
        ativo=True,
        nivel=NivelPermissao.ADMINISTRADOR,
    ).exists()


def usuarios_admin_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not _pode_gerenciar_usuarios(request.user):
            raise PermissionDenied("Você não possui permissão para administrar usuários e permissões.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def _proteger_superusuario(request, usuario_alvo):
    if usuario_alvo.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("Somente um superusuário pode alterar outro superusuário.")


@usuarios_admin_required
def lista_usuarios(request):
    busca = (request.GET.get("q") or "").strip()
    cargo = (request.GET.get("cargo") or "").strip()
    status = (request.GET.get("status") or "").strip()

    usuarios = (
        User.objects
        .select_related("perfil_erp")
        .annotate(total_modulos=Count("permissoes_modulos_erp", filter=Q(permissoes_modulos_erp__ativo=True), distinct=True))
        .order_by("first_name", "last_name", "username")
    )

    if busca:
        usuarios = usuarios.filter(
            Q(first_name__icontains=busca)
            | Q(last_name__icontains=busca)
            | Q(username__icontains=busca)
            | Q(email__icontains=busca)
        )
    if cargo:
        usuarios = usuarios.filter(perfil_erp__cargo=cargo)
    if status == "ativos":
        usuarios = usuarios.filter(is_active=True)
    elif status == "inativos":
        usuarios = usuarios.filter(is_active=False)

    context = {
        "usuarios": usuarios,
        "busca": busca,
        "cargo_selecionado": cargo,
        "status_selecionado": status,
        "cargos": PerfilUsuario.Cargo.choices,
        "total_usuarios": User.objects.count(),
        "total_ativos": User.objects.filter(is_active=True).count(),
        "total_inativos": User.objects.filter(is_active=False).count(),
        "total_com_acesso": User.objects.filter(permissoes_modulos_erp__ativo=True).distinct().count(),
    }
    return render(request, "usuarios/lista.html", context)


@usuarios_admin_required
def novo_usuario(request):
    if request.method == "POST":
        form = UsuarioSistemaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                usuario = form.save()
            messages.success(request, "Usuário criado. Agora configure os módulos e permissões.")
            return redirect("usuarios:configurar_usuario", usuario_id=usuario.pk)
    else:
        form = UsuarioSistemaForm()

    return render(request, "usuarios/formulario.html", {
        "form": form,
        "modo_criacao": True,
        "usuario_alvo": None,
    })


@usuarios_admin_required
def configurar_usuario(request, usuario_id):
    usuario_alvo = get_object_or_404(User.objects.select_related("perfil_erp"), pk=usuario_id)
    _proteger_superusuario(request, usuario_alvo)

    if request.method == "POST":
        form = UsuarioSistemaForm(request.POST, instance=usuario_alvo, usuario_alvo=usuario_alvo)
        if form.is_valid():
            with transaction.atomic():
                usuario = form.save()
                salvar_configuracao_modulos_usuario(usuario, request.POST, usuario_executor=request.user)
            if usuario.pk == request.user.pk and form.cleaned_data.get("senha"):
                update_session_auth_hash(request, usuario)
            messages.success(request, "Usuário, módulos e permissões atualizados com sucesso.")
            return redirect("usuarios:configurar_usuario", usuario_id=usuario.pk)
    else:
        form = UsuarioSistemaForm(instance=usuario_alvo, usuario_alvo=usuario_alvo)

    modulos = obter_configuracao_modulos_usuario(usuario_alvo)
    return render(request, "usuarios/configurar.html", {
        "form": form,
        "usuario_alvo": usuario_alvo,
        "modulos": modulos,
    })


@usuarios_admin_required
@require_POST
def alternar_status_usuario(request, usuario_id):
    usuario_alvo = get_object_or_404(User, pk=usuario_id)
    _proteger_superusuario(request, usuario_alvo)
    if usuario_alvo.pk == request.user.pk and usuario_alvo.is_active:
        messages.error(request, "Você não pode desativar o próprio usuário.")
        return redirect("usuarios:lista_usuarios")

    usuario_alvo.is_active = not usuario_alvo.is_active
    usuario_alvo.save(update_fields=["is_active"])
    perfil = getattr(usuario_alvo, "perfil_erp", None)
    if perfil:
        perfil.ativo = usuario_alvo.is_active
        perfil.save(update_fields=["ativo", "atualizado_em"])

    estado = "ativado" if usuario_alvo.is_active else "desativado"
    messages.success(request, f"Usuário {estado} com sucesso.")
    return redirect("usuarios:lista_usuarios")


@usuarios_admin_required
@require_POST
def excluir_usuario(request, usuario_id):
    usuario_alvo = get_object_or_404(User, pk=usuario_id)
    _proteger_superusuario(request, usuario_alvo)

    if usuario_alvo.pk == request.user.pk:
        messages.error(request, "Você não pode excluir o próprio usuário.")
        return redirect("usuarios:configurar_usuario", usuario_id=usuario_alvo.pk)

    nome = usuario_alvo.get_full_name() or usuario_alvo.username
    try:
        usuario_alvo.delete()
        messages.success(request, f"Usuário {nome} excluído com sucesso.")
    except ProtectedError:
        messages.error(
            request,
            "Este usuário possui registros históricos protegidos e não pode ser excluído. Desative-o para preservar o histórico.",
        )
    return redirect("usuarios:lista_usuarios")


# Compatibilidade temporária com a URL/tela criada na etapa anterior.
@usuarios_admin_required
def editar_permissoes_compras(request, usuario_id):
    return redirect("usuarios:configurar_usuario", usuario_id=usuario_id)
