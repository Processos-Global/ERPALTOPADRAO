# Testes e validações

## Referência anterior à implementação

Base `da82950`, Python 3.13.18 e Django 6.0.7, SQLite em memória verificado no perfil `relatorios.test_settings`, e-mail em memória e mídia temporária. O cenário de concretagem que simula falha no Drive gera traceback esperado. Os dois testes omitidos requerem `SELECT FOR UPDATE`.

| Comando | Resultado |
| --- | --- |
| `.venv/Scripts/python.exe manage.py check --settings=relatorios.test_settings` | Sem apontamentos. |
| `.venv/Scripts/python.exe manage.py test --settings=relatorios.test_settings --noinput --verbosity=1` | 467 executados, 465 aprovados, 2 omitidos, sem falhas. |

O executor de QA identificou MySQL 8.0.46 na instância temporária em loopback, validou o diretório de dados e confirmou os fusos `UTC` e `America/Sao_Paulo`. O `check --database default` com o grafo real reportou o aviso preexistente `mysql.W003` para o campo único `compras.SuprimentoReferencia.chave`.

## Fase 1 — Compras e Almoxarifado

- `manage.py test compras obras planejamento usuarios almoxarifado --settings=relatorios.test_settings --noinput --verbosity=1` executou 276 testes, 274 aprovados e 2 omitidos por `SELECT FOR UPDATE`.
- O Edge 158 verificou 12 combinações de telas renderizadas pelo Django em 390 e 1.366 px, claro e escuro. Os cenários incluíram criação de linhas, seleção de material, troca de obra, editor de cotação, resposta assíncrona e ausência de rolagem horizontal na página. O navegador usou respostas sintéticas de estoque. A consulta real foi verificada separadamente no Django.
- A consulta agrupada fez nove queries HTTP com autenticação e dois materiais. Fixtures cobriram IDs semelhantes, obras e unidades distintas, transferências, saída e unidade legada em branco. O saldo é serializado com quatro casas decimais.

## Fase 2 — Financeiro

- `manage.py test compras financeiro planejamento usuarios --settings=relatorios.test_settings --noinput --verbosity=1` executou 234 testes, 232 aprovados e 2 omitidos. Testes focados também exercitaram a correção por HTTP, a projeção contratada sem dupla contagem e a guarda de aprovação vigente do pagamento.
- O Edge verificou 20 combinações de página, tema e largura para a central financeira, com HTML renderizado por Django e fixtures sintéticas. Conferiu a área ativa, os links de navegação, os dados de planejamento e as ações disponíveis no histórico.
- No ensaio com grafo real em SQLite, `makemigrations --check --dry-run` indicou esquema alinhado. A aplicação e a reversão das duas novas migrações passaram sem parcelas novas. Um segundo ensaio confirmou a preservação de um vínculo legado e a recusa de reversão após inserir uma parcela irmã.

## Fase 3 — PDF de cotação

- `manage.py test compras.tests cadastros --settings=relatorios.test_settings --noinput --verbosity=1` executou 58 testes, 57 aprovados e 1 omitido por exigir bloqueio de linha.
- O pypdf confirmou os dados institucionais, uma imagem de 120 × 60 obtida via storage sem caminho local, os textos da obra e do fornecedor e a quantidade comercial. O caso de arquivo ausente produziu PDF com os dados restantes. A especificação superior à altura da página gerou múltiplas páginas com o item final presente.
- Os testes reproduziram o erro de logo inexistente e a quebra de layout antes da correção. A verificação de armazenamento remoto usa uma implementação sintética da API de storage. A publicação real permanece sujeita à homologação do ambiente.

## Retomada — Diário, concorrência e regressão integrada

Ambiente desta retomada: Linux, Python 3.13.5, Django 6.0.7 (dependências Python compatíveis reaproveitadas do ZIP e bibliotecas disponíveis no ambiente). Perfil `relatorios.test_settings`: SQLite compartilhado em memória, migrations desativadas, mídia temporária, e-mail em memória, Drive desativado. Nenhuma configuração de produção importada.

| Verificação executada | Resultado observado |
| --- | --- |
| `python manage.py test obras.test_diario_midias --settings=relatorios.test_settings --verbosity 2 --noinput` antes das correções | 9 testes: 7 aprovados, 2 falhas (upload privado e rollback). |
| Mesmo grupo após completar armazenamento e formulário, com 4 regressões adicionais | 13 testes, 13 aprovados, 0 erros, 0 falhas. |
| Primeira execução da suíte completa após corrigir o upload | 517 testes, 1 erro de bloqueio SQLite, 3 omitidos. |
| Teste de concorrência avulsa isolado antes do ajuste de espera | 5 execuções: 4 aprovadas, 1 erro `database table is locked`. |
| Teste de concorrência avulsa isolado após o ajuste de espera | 8 execuções consecutivas aprovadas. |
| `python manage.py test --settings=relatorios.test_settings --noinput --verbosity 1` — execução final | **521 testes, 518 aprovados, 3 omitidos, 0 erros, 0 falhas**; 14,292 s de testes. `System check` sem apontamentos. |
| `makemigrations --check --dry-run` em perfil SQLite temporário derivado de `relatorios.test_settings`, com `orcamento` e `MIGRATION_MODULES = {}` | `No changes detected`. |
| Suíte completa e grupo de Diário/recebimentos com grafo real de migrations em SQLite | O banco de teste foi criado e a execução dos testes começou, mas os comandos excederam o limite de execução. Sem resultado final confirmado. |
| Chromium 144 / Playwright, servidor Django de teste com dados sintéticos | A navegação em localhost retornou `ERR_BLOCKED_BY_ADMINISTRATOR`. A homologação visual não foi concluída. |
| MySQL | Servidor `mysqld` não disponível neste ambiente; validação local pendente. |

Os três testes omitidos requerem `has_select_for_update`: concorrência de recebimentos de uma mesma NF, de formalização de contratação/anexo e de necessidades de compra. O traceback de falha simulada no Drive na suíte final é esperado pelo teste de Concretagem; o resultado final foi `OK (skipped=3)`. Os ensaios antigos desta página não devem ser somados aos 521 testes.

O grupo de integração existente cobre compra independente de estoque, preservação de quantidade original e reservas legadas, recebimentos parciais, valor documentado, divergências, parcelas, frete, descontos, antecipações, aprovação, malotes por obra, confirmação, estorno e diagnóstico não destrutivo. O resultado é uma regressão automatizada em SQLite, não uma validação de dados reais ou de concorrência em MySQL.

### Repetir no ambiente local seguro

```powershell
python manage.py check --settings=relatorios.test_settings
python manage.py test --settings=relatorios.test_settings --noinput --verbosity 1
# Ajustar o caminho abaixo se o executável MySQL estiver em outro diretório.
python -m relatorios.executar_mysql_qa --mysqld "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe" --com-migrations test --noinput --verbosity 1
```

O executor existente cria uma instância temporária, com schemas e conta exclusivos de QA. Não confundir com o servidor MySQL persistente. Não usar o resultado SQLite como substituto da validação MySQL.
