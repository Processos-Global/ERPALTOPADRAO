from hashlib import sha256

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.contrib.auth.views import PasswordResetView
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def _hash_identidade(*partes):
    conteudo = "|".join(str(parte or "").strip().lower() for parte in partes)
    return sha256(conteudo.encode("utf-8")).hexdigest()


def _ip_cliente(request):
    # Em PythonAnywhere REMOTE_ADDR é suficiente para a aplicação.
    # Não confiamos diretamente em X-Forwarded-For enviado pelo cliente.
    return request.META.get("REMOTE_ADDR", "desconhecido")


def _chave_tentativas_login(request):
    usuario = request.POST.get("username") or ""
    identidade = _hash_identidade(_ip_cliente(request), usuario)
    return f"login-falhas:{identidade}"


def _registrar_falha_cache(chave, timeout):
    if cache.add(chave, 1, timeout=timeout):
        return 1
    try:
        return cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, timeout=timeout)
        return 1


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:index")

    proxima_pagina = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        chave_tentativas = _chave_tentativas_login(request)
        max_tentativas = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
        tentativas = cache.get(chave_tentativas, 0)

        if tentativas >= max_tentativas:
            form = AuthenticationForm(request=request, data=request.POST)
            form.add_error(
                None,
                "Muitas tentativas de login. Tente novamente mais tarde.",
            )
            return render(
                request,
                "usuarios/autenticacao/login.html",
                {"form": form, "next": proxima_pagina or ""},
                status=429,
            )

        form = AuthenticationForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            usuario = form.get_user()
            cache.delete(chave_tentativas)

            perfil = getattr(usuario, "perfil_erp", None)

            if perfil is not None and not perfil.ativo:
                form.add_error(
                    None,
                    "Seu perfil está desativado. Procure um administrador.",
                )
            else:
                login(request, usuario)

                messages.success(
                    request,
                    f"Bem-vindo, {usuario.get_full_name() or usuario.username}.",
                )

                if (
                    proxima_pagina
                    and url_has_allowed_host_and_scheme(
                        url=proxima_pagina,
                        allowed_hosts={request.get_host()},
                        require_https=request.is_secure(),
                    )
                ):
                    return redirect(proxima_pagina)

                return redirect("core:index")
        else:
            _registrar_falha_cache(
                chave_tentativas,
                getattr(settings, "LOGIN_LOCKOUT_SECONDS", 900),
            )
    else:
        form = AuthenticationForm(request=request)

    return render(
        request,
        "usuarios/autenticacao/login.html",
        {
            "form": form,
            "next": proxima_pagina or "",
        },
    )


class ERPPasswordResetForm(PasswordResetForm):
    """Permite recuperação apenas para usuários ativos do ERP.

    O PasswordResetForm do Django já evita revelar se o e-mail existe.
    Mantemos esse comportamento e acrescentamos a validação do perfil ERP.
    """

    def get_users(self, email):
        for usuario in super().get_users(email):
            perfil = getattr(usuario, "perfil_erp", None)
            if perfil is None or perfil.ativo:
                yield usuario


class ERPPasswordResetView(PasswordResetView):
    template_name = "usuarios/autenticacao/password_reset_form.html"
    email_template_name = "usuarios/emails/password_reset_email.txt"
    html_email_template_name = "usuarios/emails/password_reset_email.html"
    subject_template_name = "usuarios/emails/password_reset_subject.txt"
    form_class = ERPPasswordResetForm
    success_url = reverse_lazy("usuarios:password_reset_done")

    def form_valid(self, form):
        # Limita solicitações por combinação IP + e-mail sem revelar ao cliente
        # se a conta existe. Quando o limite é atingido, mostramos a mesma tela
        # de sucesso e simplesmente não enviamos outro e-mail.
        email = form.cleaned_data.get("email", "")
        identidade = _hash_identidade(_ip_cliente(self.request), email)
        chave = f"password-reset:{identidade}"

        max_tentativas = getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", 3)
        timeout = getattr(settings, "PASSWORD_RESET_LOCKOUT_SECONDS", 900)
        tentativas = cache.get(chave, 0)

        if tentativas >= max_tentativas:
            return redirect(self.get_success_url())

        _registrar_falha_cache(chave, timeout)
        return super().form_valid(form)


@require_POST
def logout_view(request):
    logout(request)

    messages.success(
        request,
        "Você saiu do sistema com segurança.",
    )

    return redirect(reverse("usuarios:login"))
