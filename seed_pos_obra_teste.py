"""Dados fictícios para testes locais do SAARI Pós-Obra.
Execute no diretório do manage.py:
python manage.py shell -c "exec(open('seed_pos_obra_teste.py', encoding='utf-8').read())"
Não cria contas de login ou OSs. Pode ser reexecutado sem duplicar os registros de teste.
"""
from datetime import date
from django.db import transaction
from django.utils import timezone
from cadastros.models.pos_obra import Cliente, EmpreendimentoPosObra, VinculoCliente

TESTES = [
    ("Maria Oliveira [TESTE]", "TESTE-CLIENTE-001", "Mansão Jardim das Palmeiras [TESTE]", "TESTE-POS-001", "Rua Fictícia 101, Brasília/DF"),
    ("João Almeida [TESTE]", "TESTE-CLIENTE-002", "Mansão Lago Sereno [TESTE]", "TESTE-POS-002", "Rua Fictícia 202, Brasília/DF"),
    ("Ana Costa [TESTE]", "TESTE-CLIENTE-003", "Mansão Vale Verde [TESTE]", "TESTE-POS-003", "Rua Fictícia 303, Brasília/DF"),
    ("Carlos Pereira [TESTE]", "TESTE-CLIENTE-004", "Mansão Horizonte [TESTE]", "TESTE-POS-004", "Rua Fictícia 404, Brasília/DF"),
    ("Fernanda Rocha [TESTE]", "TESTE-CLIENTE-005", "Mansão Bosque Azul [TESTE]", "TESTE-POS-005", "Rua Fictícia 505, Brasília/DF"),
    ("Ricardo Martins [TESTE]", "TESTE-CLIENTE-006", "Mansão Solar [TESTE]", "TESTE-POS-006", "Rua Fictícia 606, Brasília/DF"),
]

with transaction.atomic():
    clientes = []
    empreendimentos = []
    for i, (nome, documento, imovel, codigo, endereco) in enumerate(TESTES, 1):
        cliente, _ = Cliente.objects.get_or_create(
            documento=documento,
            defaults={
                "nome": nome,
                "email": f"saari.teste{i:02d}@example.com",
                "telefone": f"(61) 90000-{i:04d}",
                "ativo": True,
                "portal_habilitado": False,
            },
        )
        empreendimento, _ = EmpreendimentoPosObra.objects.get_or_create(
            codigo_historico=codigo,
            defaults={
                "nome_historico": imovel,
                "endereco_historico": endereco,
                "historica": True,
                "data_entrega": date(2025, 6, min(i * 3, 28)),
                "liberada": True,
                "liberado_em": timezone.now(),
            },
        )
        VinculoCliente.objects.get_or_create(
            cliente=cliente,
            empreendimento=empreendimento,
            defaults={"papel": "PROPRIETARIO", "ativo": True},
        )
        clientes.append(cliente)
        empreendimentos.append(empreendimento)

print(f"OK: {len(clientes)} clientes e {len(empreendimentos)} mansões históricas de teste conferidos.")
print("Vínculos de proprietário criados ou preservados; imóveis novos ficam liberados para Pós-Obra.")
print("Nenhuma OS foi criada: abra as ordens manualmente para testar o fluxo.")
