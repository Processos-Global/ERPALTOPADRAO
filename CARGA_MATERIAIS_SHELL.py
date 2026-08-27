"""
USO (PowerShell, na raiz do projeto):

1. Instale openpyxl se necessário:
   pip install openpyxl

2. Ajuste ARQUIVO abaixo para o caminho da sua planilha.

3. Execute:
   python manage.py shell < CARGA_MATERIAIS_SHELL.py

Este é apenas um script de carga inicial pelo terminal; não cria endpoint nem comando permanente no ERP.
"""
from openpyxl import load_workbook
from django.db import transaction

from cadastros.models import AtividadeMaterial, Material, SubatividadeMaterial, UnidadeMedida

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


wb = load_workbook(ARQUIVO, read_only=True, data_only=True)
ws = wb[wb.sheetnames[0]]
rows = ws.iter_rows(values_only=True)
headers = [limpar(v).upper() for v in next(rows)]

esperados = ["ATIVIDADE", "SUBATIVIDADE", "MATERIAL", "VARIAÇÃO / ESPECIFICAÇÃO", "UNIDADE"]
if headers != esperados:
    raise RuntimeError(f"Cabeçalho inesperado. Encontrado: {headers}")

criados = 0
existentes = 0
erros = []

with transaction.atomic():
    for numero_linha, row in enumerate(rows, start=2):
        atividade_nome, subatividade_nome, material_nome, especificacao, unidade_sigla = map(limpar, row)

        if not material_nome:
            continue

        if not atividade_nome or not subatividade_nome or not unidade_sigla:
            erros.append((numero_linha, row, "Atividade, subatividade e unidade são obrigatórias."))
            continue

        unidade, _ = UnidadeMedida.objects.get_or_create(
            sigla=unidade_sigla,
            defaults={"descricao": DESCRICOES_UNIDADE.get(unidade_sigla, DESCRICOES_UNIDADE.get(unidade_sigla.lower(), unidade_sigla))},
        )
        atividade, _ = AtividadeMaterial.objects.get_or_create(nome=atividade_nome)
        subatividade, _ = SubatividadeMaterial.objects.get_or_create(
            atividade=atividade,
            nome=subatividade_nome,
        )

        _, created = Material.objects.get_or_create(
            atividade=atividade,
            subatividade=subatividade,
            nome=material_nome,
            especificacao=especificacao,
            unidade=unidade,
        )
        if created:
            criados += 1
        else:
            existentes += 1

print("\nCARGA CONCLUÍDA")
print(f"Materiais criados: {criados}")
print(f"Materiais já existentes: {existentes}")
print(f"Atividades: {AtividadeMaterial.objects.count()}")
print(f"Subatividades: {SubatividadeMaterial.objects.count()}")
print(f"Unidades: {UnidadeMedida.objects.count()}")
print(f"Total de materiais: {Material.objects.count()}")
if erros:
    print(f"\nLinhas com erro: {len(erros)}")
    for erro in erros[:20]:
        print(erro)
