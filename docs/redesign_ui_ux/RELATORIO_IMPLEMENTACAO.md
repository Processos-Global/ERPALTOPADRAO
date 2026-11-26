# Implementação do redesign

O trabalho parte do layout existente em Django. A base passou a compartilhar tokens, tema e controles. O painel inicial dá acesso direto aos módulos autorizados e concentra favoritos, recentes e notificações. O símbolo e o logotipo originais continuam nas superfícies em que eram usados.

| Área | Alterações de interface |
| --- | --- |
| Painel geral e navegação | Cards menores, menu com seções, subseções, estado ativo, busca local por atalhos de teclado, favoritos, recentes, contexto e perfil. |
| Financeiro | Hierarquia dos indicadores, agenda, filtros adicionais, células monetárias, estados de vencimento, disponibilidade para pagamento e aprovação. Listagens de títulos usam retorno autorizado e ações relacionadas. |
| Compras e Contratos | Painel, processos, pedidos, formulários, matriz e relatórios de grandes fornecedores adotam superfícies e estados comuns. Listas vinculam filtros ao detalhe. O resumo de pedidos mantém carregamento sob demanda. A página de Contratos usa as superfícies do módulo Compras onde o fluxo existe. |
| Planejamento e Suprimentos | Menus, cronogramas, quadro, importações e grandes fornecedores usam paleta comum e sinais de progresso mais legíveis. Séries, textos, grade e tooltip do cronograma físico acompanham o tema. O fluxo comercial detalhado continua carregando sob demanda. |
| Obras, Ficha Técnica, Almoxarifado, Diário, FVS, Vistorias e Concretagem | Estilos operacionais compartilhados, áreas roláveis delimitadas, formulários e ações adequados para uso em campo, controles com rótulos e estados, navegação por teclado em etapas e modais de Concretagem, retorno contextual nas rotas operacionais. |
| Projetos e Orçamento | Cabeçalhos, filtros, checklists, alterações e superfícies usam os tokens base. As listas de documentos e histórico continuam usando as permissões e a paginação existentes. |
| Pós-Obra e Portal | Listas, quadro, agenda, formulários, ordem de serviço e portal adotam as superfícies de cada tema. O retorno ao quadro ou à lista mantém consulta e âncora. |
| Cadastros e Usuários | Cabeçalhos e tabelas comuns, formulários mais claros, ações visíveis e organização de permissões. |
| Autenticação e notificações | Login e recuperação usam tema compartilhado. A central exibe contagem e estado de leitura, conserva as ações POST e os formulários com CSRF. |
| Indicadores | ECharts acompanha as mudanças de tema. Os filtros e os downloads usam as rotas existentes. |

As rotas de Diário de Obra, Vistorias e Almoxarifado estão no aplicativo Obras. A operação de Suprimentos aparece em Planejamento e Compras. Contratos usa rotas de Compras. O aplicativo Integrações não tinha páginas próprias para adaptar.

## Arquivos de referência

- Estrutura e navegação em `templates/layouts/base.html`, `templates/components/`, `templates/core/index.html`, `core/views/index.py`, `usuarios/context_processors.py`, `usuarios/services/navegacao.py` e `static/js/saari-navigation.js`.
- Tema, Design System e dropdown em `static/css/saari-*.css`, `static/css/base.css`, `static/js/saari-theme.js`, `static/js/saari-select-search.js` e `static/relatorios/`.
- Retorno validado em `core/templatetags/saari_contexto.py`.
- Adaptações específicas em `templates/{financeiro,compras,planejamento,obras,projetos,orcamento,pos_obra,cadastros,usuarios}/` e em CSS de Obras, Cadastros e autenticação.
- Verificação em `usuarios/test_navegacao_erp.py`, `core/test_contexto_navegacao.py`, `pos_obra/test_redesign_navegacao.py` e no perfil isolado `relatorios/test_settings.py`.

O cenário de Pós-Obra que verificava a presença do link no painel foi atualizado para conceder à conta de teste a permissão explícita exigida pela view. Um caso separado verifica a ausência do link para a conta que possui apenas o cargo.
