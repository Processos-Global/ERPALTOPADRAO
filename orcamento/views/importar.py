from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from obras.models import Obra


@login_required
def inserir_orcamento(request):
    obras = Obra.objects.all()

    if request.method == "POST":
        obra_id = request.POST.get("obra")
        arquivo = request.FILES.get("arquivo_csv")

        erros = []
        if not obra_id:
            erros.append("Selecione uma obra.")
        if not arquivo:
            erros.append("Selecione um arquivo CSV.")

        obra_selecionada = None
        if obra_id:
            obra_selecionada = Obra.objects.filter(pk=obra_id).first()
            if not obra_selecionada:
                erros.append("Obra selecionada é inválida.")

        if erros:
            return render(
                request,
                "orcamento/inserir_orcamento.html",
                {"obras": obras, "erros": erros, "obra_id": obra_id},
            )

        # A leitura do arquivo CSV ainda não foi implementada.
        return render(
            request,
            "orcamento/inserir_orcamento.html",
            {
                "obras": obras,
                "arquivo_recebido": arquivo.name,
                "obra_selecionada": obra_selecionada,
            },
        )

    return render(request, "orcamento/inserir_orcamento.html", {"obras": obras})
