# Auditoria técnica e visual — SAARI Relatórios

Auditoria inicial em 2026-11-11, realizada por cinco subagentes reais com seleção nominal dos perfis configurados. Nenhum deles alterou código durante o diagnóstico. Referências abaixo correspondem ao código anterior à implementação; consultar o Git para comparar.

## Backend

- `relatorios/views/painel.py`, `_auth` e `_render`: somente permissão do módulo; faltam ações visualizar/exportar previstas em `usuarios/services/registro_permissoes.py`. Usar `possui_permissao_acao` existente, sem criar política de acesso aos módulos-fonte.
- `_filters`: isdigit/int pode falhar com Unicode; filtro inválido vira consolidado; empreendimento validado por chamados exclui cadastro legítimo vazio.
- `_apply` e `analises.range_dt`: dia seguinte a date.max causa overflow. `_series` agrupa UTC com intervalo local, deslocando viradas de mês.
- CSV omite filtros de obra/empreendimento e não identifica rankings resumidos; proteção contra fórmulas já existe e deve permanecer.
- Fornecedores são agrupados por nome não único. Agregações do ticket são repetidas. Visão geral calcula todo planejamento para descartar seus painéis.
- Não foi encontrado N+1 comprovado: select_related/only já cobrem relações dos loops examinados. Não há justificativa para alterações de schema ou índices sem medição.
- Cenários de performance ainda não medidos: materialização de snapshots, rankings ordenados em Python e mediana de durações em memória. São riscos de volume, não lentidão comprovada.

## Dados e BI

Inventários completos em [auditoria-indicadores.md](auditoria-indicadores.md) e [auditoria-bi.md](auditoria-bi.md). Conclusões centrais: saldo original não é devido líquido; cobertura de pesquisa usa conjuntos incompatíveis; aging está deslocado; economia ignora descontos e deve ser explicitamente bruta; ausência não é zero; desvio em p.p. deve preservar sinal; as séries financeiras devem ser temporais.

## Frontend

- Identidade efetiva combina `static/css/base.css`, overrides de `templates/layouts/base.html` e `components/saari_theme.html`, incluído após extra_css. Não copiar cores de um arquivo isolado.
- Fontes existentes: Plus Jakarta Sans e Source Serif 4. Não há necessidade de adicionar Bootstrap ou substituir CSS próprio.
- Título de relatório chega a 40px; referências de Planejamento e Compras usam cerca de 25 e 30px. KPIs de 142px e grandes paddings aumentam espaços sem conteúdo.
- Primeiro painel ocupa duas colunas por posição e ganha altura; substituir por metadado explícito quando necessário.
- Aba ativa escura combina token de texto claro como fundo com texto branco; ajustar contraste.
- Preservar classes locais, temas, filtros, navegação horizontal, tabela, CSV, impressão, resize e PNG.
- Extrair CSS/JS específicos, componente de painel reutilizável, sem mexer nos templates dos demais módulos. Captions devem permanecer curtas ou expansíveis; sem busca ou texto decorativo.

## QA

- Testes iniciais eram apenas scaffold. Dependências confirmadas por import sem configurar Django: Python 3.14.4, Django 6.0.7, SQLite 3.50.4.
- `config.settings` lê .env; usar settings independentes e SQLite exclusivamente em memória, migrations desativadas. Não executar migrações nem acessar bancos existentes.
- Cobrir ações de permissão, filtros vazios/inválidos/extremos, datas inclusivas e fronteiras, financeiro/estorno, amostras de FVS, aging, cobertura pesquisa, snapshots, ausências/negativos no contrato de gráficos, escape HTML/CSV e sete endpoints.
- Particularidades MySQL, volume real, reconciliação de dados e aspecto visual no navegador dependem de verificação adicional; não declarar sucesso com base apenas em inspeção estática.

## Decisões do coordenador

O [plano técnico](plano-tecnico.md) elimina propostas duplicadas e separa correções comprovadas de melhorias futuras. Regra financeira continua de pagamento integral singular. Economia líquida, custo total de pós-obra, prazos documentais inexistentes e pesos físicos corporativos não serão inventados. Cada arquivo terá somente um editor durante a implementação.
