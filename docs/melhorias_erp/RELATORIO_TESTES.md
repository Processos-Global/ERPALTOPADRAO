# Testes

Python 3.13.18 na virtualenv existente. Todos os comandos Django abaixo usaram SQLite em memória e mídia temporária. O módulo de settings isolado não importa a configuração da aplicação nem o arquivo de ambiente.

| Verificação | Resultado |
| --- | --- |
| `manage.py check --settings=relatorios.test_settings` | Nenhum problema |
| `manage.py test --settings=relatorios.test_settings --noinput` antes das mudanças | 325 aprovados |
| `manage.py test --settings=relatorios.test_settings --noinput` com a entrega integrada | 347 aprovados |
| Compras, Obras, Planejamento, Projetos e Pós-Obra com a cadeia de middlewares da aplicação adicionada ao settings isolado | 288 aprovados |
| Duas verificações temporárias com cliente do portal, CSRF obrigatório e quatro rotas novas | 12 subcasos aprovados |
| `manage.py makemigrations --check --dry-run` com módulo temporário derivado de `relatorios.test_settings`, incluindo `orcamento` e o grafo de migrações | Nenhuma mudança detectada |
| Compilação de templates Django alterados e novos | 25 compilados |
| `git diff --check` | Sem erros de whitespace |

A primeira tentativa de executar a suíte integral com `obras.test_settings_concretagem` encontrou a guarda de `relatorios.tests`, que exige `relatorios.test_settings`. A suíte integral foi repetida com o settings exigido. Durante a implementação, testes novos falharam antes das respectivas correções e passaram na execução integrada. O log de falha de envio ao Drive é emitido por um cenário de teste de concretagem que verifica o tratamento de erro.

As regressões abrangem paginação e filtros de Diário e Projetos, separação dos checklists, recorte de Vistorias, itens e materiais da Ficha Técnica, PDFs e Excel, abas e períodos do Cronograma Físico, detalhe de Suprimentos, relatório de Grandes Fornecedores, SLA, histórico, pedidos e cobertura de necessidade em Compras.

Sete cenários do carregamento global e localizado foram exercitados no V8. A compilação JavaScript passou em oito blocos de navegação, Diário, Ficha Técnica, Suprimentos e detalhe de Compras. Um bloco de Compras contém interpolação Django e foi excluído da compilação direta do arquivo. O Edge headless falhou ao iniciar o processo gráfico. Capturas e inspeção visual de claro, escuro e tamanhos de tela ficaram pendentes.

A suíte isolada não comprova planos de execução ou bloqueios concorrentes no MySQL. Validar em homologação o saldo de estoque sob operações simultâneas, as consultas de Compras com a massa representativa e os arquivos estáticos e exports no navegador.
