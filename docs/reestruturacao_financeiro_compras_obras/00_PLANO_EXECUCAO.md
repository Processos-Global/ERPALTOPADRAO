# Plano de execução

Base `da82950` na branch `main`, com árvore limpa. O pedido autoriza as fases 0 a 6 em sequência. Python 3.13.18 e Django 6.0.7 estão instalados na `.venv`. O perfil `relatorios.test_settings` usa SQLite exclusivamente em memória, diretórios temporários de mídia, e-mail em memória e Drive desativado. O perfil padrão configura MySQL por ambiente.

## Dependências e entregas

1. Compras e Almoxarifado. Separar `NecessidadeCompra.quantidade_necessaria` da quantidade comercial `quantidade_incluida`, remover gatilhos de reserva e validações de cobertura, preservar limites de pedidos e recebimentos e consultar estoque físico agrupado por obra, material e unidade. Cobrir criação, edição, aprovação, emissão, consulta e movimentação com fixtures sintéticas. Inspecionar reservas legadas sem alterar bases existentes.
2. Financeiro. Preservar `PedidoCompra` como compromisso, iniciar obrigações normais no serviço transacional de recebimento, reaproveitar liberações como vínculo técnico e usar `TituloPagar` e seu ciclo de aprovação. Reconciliar nota, itens, frete e antecipações antes da aprovação. Ajustar central, pagamentos, malotes, navegação e o consumo em planejamento, preservando as obrigações históricas e contratuais. Testar recebimentos parciais, divergência, documentos, concorrência, saldos, cancelamentos, aprovações, malotes e estornos.
3. PDF. Corrigir o cabeçalho institucional compartilhado pelos PDFs de Compras. Usar `DadosEmpresa.atual()` e a API de storage do logotipo. Conferir texto, imagens, acesso e paginação no arquivo gerado.
4. Diário de Obra. Atuar no app `obras`, que possui os modelos, rotas e telas reais. Exibir fotos com miniaturas sob demanda e ampliação acessível, mantendo escopo, atividades e concretagens. Testar autorização, arquivos indisponíveis, quantidade de consultas e navegação com teclado e celular.
5. Integração. Verificar pedido, compromisso, recebimento, estoque, cronograma, solicitação, aprovação e malote com valores reconciliados e fixtures isoladas.
6. Validação. Executar checks, suíte completa, validação do grafo real de migrações e, se disponível, MySQL descartável e Edge. Consolidar homologação e instruções de atualização e recuperação.

## Diagnóstico e riscos iniciais

- `compras/services/processos.py`, `etapas.py` e `pedidos.py` usam cobertura em etapas diferentes. `obras/views/estoque.py` ainda desconta reserva de saídas e transferências. `obras/services/estoque.py` deriva o saldo das quantidades recebidas e movimentos físicos.
- `financeiro/services/previsoes.py` cria títulos provisórios por sinal. `financeiro/services/liberacoes.py` vincula recebimento, candidata e título após uma decisão manual. Permissões, parcelamento, adiantamentos e previsões exigem verificação cruzada.
- `compras/services/pdf_empresa.py` lê o logo pelo caminho local. A regra de cadastro institucional é `DadosEmpresa.atual()`, usada também na tela de Cadastros.
- A lista de Diário é o detalhe existente e usa originais das fotos. Compartilha atividades e concretagens em consultas agrupadas.
- Reservas consumidas, pedidos emitidos, pagamentos, liberações históricas e documentos precisam manter seus vínculos. Os ensaios usam dados sintéticos e as ferramentas legadas permanecem para diagnóstico.
