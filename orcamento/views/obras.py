from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from obras.models import Obra


@login_required
def lista_obras(request):
    obras = Obra.objects.all().order_by("nome")
    return render(request, "orcamento/obras_lista.html", {"obras": obras})
