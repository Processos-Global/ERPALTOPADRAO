# Verificações da reestruturação financeira

## Ambientes

- Python 3.13.18, Django 6.0.7 e SQLite em memória no perfil `relatorios.test_settings`. A Concretagem usa o mesmo banco, mídia temporária, Drive simulado e e-mail em memória.
- MySQL 8.0.46 descartável com InnoDB `DYNAMIC`, páginas de 16 KiB e `utf8mb4`. O executor usa conta e schemas exclusivos a cada execução. Configura os fusos `UTC` e `America/Sao_Paulo` e verifica uma data atual e outra durante o horário de verão. A conversão no MySQL precisa dos dois nomes de fuso porque o Django passa `UTC` ao `CONVERT_TZ`.
- Os 99 aprovados informados na retomada, 75 de Financeiro, 12 de Compras, 11 de Ficha Técnica e 1 de Projetos, antecedem as novas alterações.

## Comandos reproduzíveis

```powershell
$python = '.venv/Scripts/python.exe'
$mysqld = 'C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqld.exe'
& $python manage.py check --settings=relatorios.test_settings
& $python manage.py test obras.tests_concretagem obras.tests_concretagem_execucao obras.tests_concretagem_mapa --settings=obras.test_settings_concretagem --verbosity 1
& $python manage.py test financeiro obras.test_ficha_consulta projetos.tests compras.tests.test_desempenho_views --settings=relatorios.test_settings --verbosity 1
& $python manage.py test --settings=relatorios.test_settings --verbosity 1 --noinput
& $python manage.py test financeiro/tests --settings=relatorios.test_settings --verbosity 1
& $python -m relatorios.executar_mysql_qa --mysqld $mysqld --com-migrations check --database default
& $python -m relatorios.executar_mysql_qa --mysqld $mysqld --com-migrations makemigrations --check --dry-run
& $python -m relatorios.executar_mysql_qa --mysqld $mysqld --com-migrations migrate --plan --noinput
& $python -m relatorios.executar_mysql_qa --mysqld $mysqld --com-migrations test --verbosity 1 --noinput
```

Acrescente rótulos Django após `test` para focar módulos. `--com-migrations` habilita o grafo real. Sem a opção, os models geram as tabelas no banco descartável. O executor define o módulo Django antes da inicialização do comando e recusa argumentos que o substituam ou alterem o caminho de importação. A Concretagem valida o perfil antes de preparar fixtures e na coleta de testes. O traceback de falha do Drive vem de um cenário simulado.

## Verificações observadas

| Execução | Resultado |
| --- | --- |
| Concretagem, configuração SQLite original | 102 aprovados |
| Concretagem e proteção do executor, SQLite | 105 aprovados |
| Regras puras em `financeiro/tests` | 5 aprovados |
| Financeiro, Ficha Técnica, Projetos e desempenho de Compras, SQLite | 105 aprovados |
| `check` SQLite, `makemigrations --check --dry-run` e `migrate --plan` MySQL | Check SQLite limpo, nenhum drift, plano gerado. Aviso MySQL remanescente `mysql.W003`. |
| MySQL focado inicial, Concretagem, Relatórios e unicidade | 146 aprovados |
| Planejamento Financeiro após carregar `UTC` e `America/Sao_Paulo`, MySQL | 5 aprovados |
| Cobertura de estoque e reserva simultânea, MySQL | 13 aprovados |
| Suíte completa, MySQL 8.0.46 com migrations reais | 447 aprovados, 0 falhas, 0 omitidos. Testes executados em 33,511 s. |
| Suíte completa, SQLite em memória | 445 aprovados, 0 falhas, 2 omitidos por ausência de `SELECT FOR UPDATE`. Testes executados em 17,018 s. |

### Suíte completa por módulo

| Módulo | MySQL aprovados | SQLite aprovados |
| --- | ---: | ---: |
| Cadastros | 8 | 8 |
| Compras | 62 | 60 |
| Financeiro | 81 | 81 |
| Obras, incluindo 102 de Concretagem e 11 de Ficha Técnica | 139 | 139 |
| Planejamento | 39 | 39 |
| Pós-Obra | 73 | 73 |
| Projetos | 1 | 1 |
| Relatórios | 30 | 30 |
| Usuários | 14 | 14 |
| **Total** | **447** | **445** |

Os dois casos de Compras omitidos no SQLite são as corridas de contratação ativa e reserva de estoque. Ambos passaram no MySQL. Os cinco testes puros de `financeiro/tests` são uma execução complementar ao comando padrão de descoberta.

Os testes financeiros cobrem POST idempotente, concorrência, aprovação no ciclo vigente, rollback de anexos, liberação parcial, frete, programação, efetivação, estorno, exportação e proteção do portal. As migrations de unicidade tiveram ensaio SQLite com reversão e dados sintéticos. Os DDLs novos foram aplicados no schema de teste MySQL.

A execução MySQL da suíte completa revelou dois pressupostos dependentes de SQLite. O teste de SLA passou a buscar os IDs das fixtures por número após `bulk_create()`. A asserção de consulta em Pós-Obra passou a usar `connection.ops.quote_name()`. As verificações de ordenação e quantidade foram mantidas. Ambos os cenários passaram isoladamente e na suíte completa em MySQL.

## Navegador

O Edge executou HTML e arquivos produzidos pelo Django com dados sintéticos, reproduzidos por um servidor local de homologação. A matriz compara `94dc49c` com a árvore de trabalho em 1366 px, 768 px e 390 px, claro e escuro. A verificação interativa incluiu teclado, filtros, foco em modal, busca assíncrona, consulta bancária restrita à seleção e downloads de PDF, Excel e CSV. A suíte Django cobre as operações de gravação e transação.

- 31 páginas, 186 combinações e 366 capturas. Uma rota histórica não possuía equivalente na revisão anterior. Depois das correções, foram repetidas 60 combinações das telas afetadas. O relatório final registra zero overflow na página, zero mensagens inesperadas de console e zero falhas de rede na reprodução local.
- Foram confirmados 20 fluxos de interação e seis arquivos de download abertos e conferidos com leitores de PDF, Excel e CSV. A reprodução serviu bibliotecas e fontes localmente. A navegação interna do Portal continua com rolagem própria no celular.
- Os títulos das telas Compras e Suprimentos passaram de aproximadamente 1,03:1 para 12,63:1 no escuro. Na página de Ordens de Serviço, o título passou de 1,00:1 para 10,98:1. A marca do Portal passou de 1,47:1 para 13,27:1.

Artefatos locais em `C:/Users/rhuan/AppData/Local/Temp/saari-ux-validation/c3-4f4bbda/`. Consulte `report-matrix-final.json`, `report-interaction.json`, `report-downloads.json`, `report-contrast.json`, `comparativo-1366.png`, `comparativo-768.png`, `comparativo-390.png` e `screens/`. Essa rodada usa Edge e dimensões emuladas. A matriz não comprova o comportamento de CDN ou dispositivos físicos.
