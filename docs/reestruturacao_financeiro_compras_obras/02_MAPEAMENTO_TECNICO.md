# Mapeamento técnico

## Fase 1 — Compras e Almoxarifado

| Camada | Implementação |
| --- | --- |
| Modelos | `compras.models.NecessidadeCompra`, `PedidoCompraItem`, `RecebimentoPedidoItem`, `ReservaEstoqueCompra`, `obras.models.MovimentoEstoque` e `cadastros.models.Material`. |
| Serviços | `compras/services/processos.py` cria e edita as quantidades. `etapas.py` e `pedidos.py` conduzem aprovação e emissão. `obras/services/estoque.py` calcula saldos e preserva a valorização e os movimentos físicos. |
| Views e formulários | `compras/views/processos.py` e `acoes.py` usam os formulários de abertura e cotação em `compras/forms/`. `compras/views/estoque.py` responde à consulta agrupada. `obras/views/estoque.py` valida o saldo para saídas e transferências. |
| Rotas | `compras:estoque_materiais_obra` recebe `obra` e parâmetros `material` repetidos. A rota histórica `compras:cobertura_necessidade` segue protegida. |
| Interface | `templates/compras/processo_form.html`, `compra_avulsa_form.html`, `processo_detalhe.html` e `static/js/compras-estoque.js`. O saldo é carregado sob demanda e a compra pode ser enviada se a consulta falhar. |
| Permissões | A consulta usa `VISUALIZAR` de Compras. Criação e edição continuam usando `SOLICITAR`. A configuração operacional deixa de oferecer a antiga exceção de estoque. |
| Integração | Entradas físicas vêm de `RecebimentoPedidoItem`. Saídas e transferências vêm de `MovimentoEstoque`. O estoque consultivo não cria registros. Os vínculos com cronogramas continuam nas rotas e serviços de Compras e Planejamento. |

## Fase 2 — Financeiro

`compras/services/pedidos.py` registra a entrega sob bloqueio de pedido e chama `financeiro/services/solicitacoes_recebimentos.py`. A origem fiscal fica em `RecebimentoPedido` e seus itens. `LiberacaoFinanceiraPedido` guarda a conciliação e `TituloPagar` referencia o recebimento. O `HistoricoTituloFinanceiro` guarda o detalhamento de quantidades, valores unitários, frete e divergência. `financeiro/signals.py` usa a sincronização de `services/previsoes.py` para manter integrações e condições históricas.

A central usa `financeiro/views/aprovacoes.py` e `services/aprovacoes.py`. A edição e as decisões de título passam por `views/titulos.py`. O malote usa `views/relatorios.py`, `RelatorioPagamento` e `ItemRelatorioPagamento`. A programação e a efetivação são serviços em `services/pagamentos.py`. Compromissos, previsão e gráficos consultam `services/compromissos.py`, `planejamento_financeiro.py` e `fluxo_caixa.py`.

## Fase 3 — PDF de cotação

A rota `compras:pdf_solicitacao_cotacao` usa a permissão `VISUALIZAR`, valida o fornecedor vinculado e delega a `compras/services/pdf_solicitacao_cotacao.py`. O serviço monta o documento no ReportLab. `pdf_empresa.py` obtém `DadosEmpresa.atual()` pelo mesmo critério de Cadastros. O cabeçalho abre o logotipo pelo storage e normaliza a imagem antes da composição, preservando a proporção. Essa abertura funciona também quando o storage remoto oferece somente fluxo de bytes. O arquivo institucional padrão é usado quando disponível e o texto é mantido quando não há imagem. A tabela de itens repete os cabeçalhos e admite quebra dentro de uma linha extensa.
