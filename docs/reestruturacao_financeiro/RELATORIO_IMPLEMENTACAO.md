# Implementação da reestruturação

A revisão começou em `main` no commit `4f4bbda`, com árvore limpa. Ele reúne as alterações anteriores e as correções manuais de compatibilidade em Financeiro, Compras, Ficha Técnica e Projetos. A retomada preservou as quatro migrations anteriores e tratou as pendências encontradas em testes e homologação.

| Alteração | Arquivos centrais |
| --- | --- |
| Testes reais de Concretagem em SQLite e MySQL isolados | `obras/tests_concretagem.py`, `relatorios/tests.py`, `relatorios/isolamento_testes.py`, `relatorios/settings_mysql_qa.py`, `relatorios/executar_mysql_qa.py` |
| Compatibilidade de fixtures e asserções SQL com os dois bancos | `compras/test_sla.py`, `pos_obra/test_ui.py` |
| Unicidade do documento de Fornecedor preenchido | `cadastros/models/fornecedores.py`, `cadastros/views/cadastros.py`, migrations `0017`–`0018` e `diagnosticar_documentos_fornecedores` |
| Contratação ativa única por processo e fornecedor | `compras/models/fluxo.py`, `compras/services/contratacao.py`, migrations `0042`–`0043` e `diagnosticar_contratacoes_duplicadas` |
| Índice integral no histórico de Suprimentos | `compras/tests/test_historico_suprimentos.py` valida 500 caracteres e os vínculos de consulta. O esquema foi preservado. |
| Visão Geral com recorte consistente | `financeiro/views/dashboard.py`, `financeiro/services/agenda.py`, `financeiro/views/pagamentos.py` e seus templates |
| Notificações restritas à permissão real e CSV protegido | `financeiro/services/permissoes.py`, `financeiro/services/notificacoes.py`, comandos de diagnóstico e testes de exportação |
| Anexos distintos com mesmo nome e tamanho e limpeza no rollback | `financeiro/services/solicitacoes_avulsas.py`, `financeiro/test_solicitacao_avulsa.py` |
| Reserva simultânea sem duplicar saldo | `compras/test_estoque_cobertura.py` |
| Histórico de Suprimentos por teclado, contraste no escuro e responsividade | `templates/planejamento/cronograma_suprimentos.html`, `templates/compras/relatorio_grandes_fornecedores.html`, `templates/components/saari_theme.html`, `templates/pos_obra/_styles.html`, `templates/pos_obra/lista.html` |

O documento do fornecedor mantém a comparação de valores armazenados, inclusive pontuação e fornecedores inativos. Documentos vazios correspondem a `NULL` no índice. As contratações canceladas têm marcador nulo, permitindo preservar o histórico do mesmo processo e fornecedor. As migrations selecionam apenas os registros incompatíveis na etapa de verificação. Os dois `models.W036` deixaram de ocorrer.

O `mysql.W003` permanece visível e tem justificativa técnica. A execução em MySQL 8.0.46 com InnoDB `DYNAMIC`, páginas de 16 KiB e `utf8mb4` confirmou índice único completo em `SuprimentoReferencia.chave`, com `SUB_PART` nulo, aceitou duas chaves de 500 caracteres que só diferiam no final e rejeitou a duplicata. Um hash do texto poderia permitir duas chaves que a collation atual considera iguais. O [procedimento de publicação](INSTRUCOES_DEPLOY.md) inclui o diagnóstico somente leitura para confirmar as características do ambiente hospedado.

O inventário atualizado pode ser obtido com `git diff --name-status` e `git ls-files --others --exclude-standard`. Para o inventário da primeira entrega, use `git diff --name-status 94dc49c..4f4bbda`. Os comandos de publicação estão em documento próprio e não foram executados.
