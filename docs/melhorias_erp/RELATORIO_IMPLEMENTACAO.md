# Implementação

| Módulo | Arquivos e resultado |
| --- | --- |
| Compras | `compras/views/processos.py`, `compras/services/sla.py`, `compras/services/cobertura_estoque.py`, URLs e templates de Compras. A listagem pagina no banco, com projeção enxuta para conservar SLA e filtros. O histórico do processo e o resumo da cobertura são consultados separadamente. |
| Almoxarifado | Cobertura em Compras usa saldo físico, reservas e pedidos da própria necessidade por FK. Saldo dos pedidos ainda não recebido fica separado do físico. Não há criação de necessidade ou reserva ao abrir o resumo. |
| Diário | `obras/views/diario.py` e templates de Diário. Paginação de 30 registros, formulários organizados em checklists de acordo com o cronograma e agrupamento complementar quando houver outras atividades. |
| Vistorias | `obras/services/resumo_vistorias.py`, `obras/views/vistorias.py` e template de resumo. A página consolidada adia a preparação e a exibição dos detalhes, com vínculo por obra que mantém os filtros. O PDF continua usando os mesmos totais. |
| Ficha Técnica | View, serviço de consulta, rotas e templates de Obras. A preparação dos itens se restringe à aba de detalhamento. A consulta oferece busca paginada de material, preservando a seleção e os filtros de exportação. |
| Planejamento | Serviços e views de cronogramas, URLs e templates de Planejamento. O Físico calcula apenas a aba escolhida. Suprimentos adia detalhes comerciais para a expansão do item da importação ativa. |
| Projetos | `projetos/views/projetos.py`, `templates/projetos/alteracoes.html` e menu. A listagem de alterações busca 15 registros por página, incluindo disciplina em uma consulta. |
| Interface comum | `static/js/app.js` e `templates/layouts/base.html` implementam indicador por formulário com adesão explícita. Foram ajustados templates em Cadastros, Pós-Obra e Indicadores para condensar textos e marcar downloads. |

O dashboard de Compras agrega indicadores em SQL, limita os cartões por coluna e preserva a ordem e a prioridade dos estados. Pedidos e anexos de Compras também foram transferidos para carregamento sob demanda. As datas de SLA exibidas usam o histórico e a data necessária na obra fica indefinida quando não há fonte oficial. Na consulta da Ficha Técnica, a página inicial agrega totais, e a abertura de um ambiente ou dos itens gerais carrega as linhas correspondentes. O relatório de Grandes Fornecedores distingue solicitado e contratado e inclui o responsável disponível. Os indicadores de Suprimentos exibem os totais filtrados.

Testes novos ou ampliados ficam nos módulos afetados. Os arquivos novos de aplicação são os templates `compras/_processo_historico.html`, `compras/_processo_pedidos.html`, `compras/necessidade_cobertura.html`, `compras/processo_secao.html` e `planejamento/_detalhe_comercial_suprimento.html`. O inventário completo pode ser conferido com `git status --short` e `git diff --stat`.

A primeira frente descrita acima antecede as migrations de prazo, frete, idempotência, programação e unicidade. O estado atual está no [relatório da reestruturação global](../reestruturacao_financeiro/RELATORIO_IMPLEMENTACAO.md).
