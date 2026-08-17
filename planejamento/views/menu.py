from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def menu_planejamento(request):
    return render(request, "planejamento/menu.html")
