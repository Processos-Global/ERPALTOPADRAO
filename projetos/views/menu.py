from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def menu_projetos(request):
    return render(
        request,
        "projetos/menu.html",
    )
