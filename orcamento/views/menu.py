from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def menu_orcamento(request):
    return render(request, "orcamento/menu.html")
