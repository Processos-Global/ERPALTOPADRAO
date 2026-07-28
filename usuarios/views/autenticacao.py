from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:index")

    proxima_pagina = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        form = AuthenticationForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            usuario = form.get_user()

            perfil = getattr(
                usuario,
                "perfil_erp",
                None,
            )

            if perfil is not None and not perfil.ativo:
                form.add_error(
                    None,
                    "Seu perfil está desativado. Procure um administrador.",
                )
            else:
                login(
                    request,
                    usuario,
                )

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
        form = AuthenticationForm(
            request=request,
        )

    contexto = {
        "form": form,
        "next": proxima_pagina or "",
    }

    return render(
        request,
        "usuarios/autenticacao/login.html",
        contexto,
    )


@require_POST
def logout_view(request):
    logout(request)

    messages.success(
        request,
        "Você saiu do sistema com segurança.",
    )

    return redirect(
        reverse("usuarios:login"),
    )