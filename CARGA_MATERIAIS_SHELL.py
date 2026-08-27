"""
CARGA INICIAL DE MATERIAIS

Execução na raiz do projeto:

    python manage.py shell < CARGA_MATERIAIS_SHELL.py

O catálogo atual de materiais utiliza:

    nome + especificacao + unidade

As colunas ATIVIDADE e SUBATIVIDADE da planilha são aceitas,
mas não são mais persistidas no cadastro de Material.
"""

from openpyxl import load_workbook
from django.db import transaction

from cadastros.models import Material, UnidadeMedida


ARQUIVO = r"Base - Lista de Materiais.xlsx"


DESCRICOES_UNIDADE = {
    "und": "Unidade",
    "un": "Unidade",
    "m": "Metro",
    "m²": "Metro quadrado",
    "m2": "Metro quadrado",
    "m³": "Metro cúbico",
    "m3": "Metro cúbico",
    "kg": "Quilograma",
    "t": "Tonelada",
    "l": "Litro",
    "L": "Litro",
    "saco": "Saco",
    "vb": "Verba",
    "cartucho": "Cartucho",
    "cx": "Caixa",
    "pc": "Peça",
    "rl": "Rolo",
}


def limpar(valor):
    return "" if valor is None else str(valor).strip()


wb = load_workbook(
    ARQUIVO,
    read_only=True,
    data_only=True,
)

ws = wb[wb.sheetnames[0]]

rows = ws.iter_rows(values_only=True)

headers = [
    limpar(valor).upper()
    for valor in next(rows)
]


esperados = [
    "ATIVIDADE",
    "SUBATIVIDADE",
    "MATERIAL",
    "VARIAÇÃO / ESPECIFICAÇÃO",
    "UNIDADE",
]


if headers != esperados:
    raise RuntimeError(
        "Cabeçalho inesperado.\n"
        f"Esperado: {esperados}\n"
        f"Encontrado: {headers}"
    )


criados = 0
existentes = 0
ignorados = 0
erros = []


with transaction.atomic():

    for numero_linha, row in enumerate(rows, start=2):

        (
            atividade_nome,
            subatividade_nome,
            material_nome,
            especificacao,
            unidade_sigla,
        ) = map(limpar, row)

        # ---------------------------------------------------------
        # MATERIAL
        # ---------------------------------------------------------

        if not material_nome:
            ignorados += 1
            continue

        # Atividade/Subatividade continuam existindo na planilha,
        # mas não fazem mais parte do cadastro do Material.

        if not unidade_sigla:
            erros.append(
                (
                    numero_linha,
                    row,
                    "Unidade é obrigatória.",
                )
            )
            continue

        # ---------------------------------------------------------
        # UNIDADE
        # ---------------------------------------------------------

        descricao_unidade = DESCRICOES_UNIDADE.get(
            unidade_sigla,
            DESCRICOES_UNIDADE.get(
                unidade_sigla.lower(),
                unidade_sigla,
            ),
        )

        unidade, _ = UnidadeMedida.objects.get_or_create(
            sigla=unidade_sigla,
            defaults={
                "descricao": descricao_unidade,
            },
        )

        # ---------------------------------------------------------
        # MATERIAL
        #
        # Catálogo atual:
        # nome + especificacao + unidade
        # ---------------------------------------------------------

        _, created = Material.objects.get_or_create(
            nome=material_nome,
            especificacao=especificacao,
            unidade=unidade,
        )

        if created:
            criados += 1
        else:
            existentes += 1


print()
print("=" * 60)
print("CARGA DE MATERIAIS CONCLUÍDA")
print("=" * 60)

print(f"Materiais criados:       {criados}")
print(f"Materiais existentes:    {existentes}")
print(f"Linhas ignoradas:        {ignorados}")
print(f"Unidades cadastradas:    {UnidadeMedida.objects.count()}")
print(f"Total de materiais:      {Material.objects.count()}")

if erros:
    print()
    print(f"Linhas com erro: {len(erros)}")

    for erro in erros[:20]:
        print(erro)

    if len(erros) > 20:
        print(
            f"... e mais {len(erros) - 20} linha(s) com erro."
        )

print("=" * 60)
