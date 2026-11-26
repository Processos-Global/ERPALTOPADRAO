# Progresso do redesign

| Etapa | Registro |
| --- | --- |
| 1. Auditoria | Estado inicial do Git registrado. HTML de 31 rotas renderizado em banco em memória e capturado no Edge em cinco larguras. Auditoria operacional acrescentou 27 rotas. |
| 2. Identidade | Identificados marrom, bronze, bege, logotipo e tipografia. O contraste dos tokens foi calculado para os dois temas. |
| 3. Design System | Tokens centralizados em `static/css/saari-tokens.css`. Componentes e integração legada passaram a CSS externo. Removidas declarações concorrentes em petróleo da base. |
| 4. Navegação | Menu hierárquico, busca, favoritos, recentes, contexto, notificações e perfil integrados à autorização das views. Testes cobrem permissões granulares e separação do portal. |
| 5. Componentes | Adotados cabeçalho, painéis, dropdown pesquisável, tabelas responsivas, mensagens com foco e feedback local. |
| 6. Dark Mode | Seletor e inicialização unificados em ERP, portal e autenticação. Gráficos acompanham a alternância. |
| 7. Módulos | Ajustes em Compras, Financeiro, Planejamento, Indicadores, Obras, Projetos, Orçamento, Pós-Obra, Cadastros e Usuários. Aplicativos com URLs vazias têm suas operações nas rotas dos módulos responsáveis. |
| 8. Responsividade e acessibilidade | Matrizes nas larguras 1920, 1366, 1280, 768 e 390 px. Corrigidos foco de saída e modal, senha por teclado, título de Concretagem e overflow de FVS. Retestes registrados. |
| 9. Testes | 467 aprovados no MySQL descartável. 465 aprovados e dois omitidos no SQLite. Verificações de filtros, três formatos de download e contraste registradas. |
| 10. Documentação | Auditoria, identidade, tokens, navegação, tema e componentes documentados. |

Os estáticos locais foram coletados em `staticfiles` com hashes conferidos. O relatório de testes registra a evidência e o checklist fica disponível para a homologação.

Na revisão posterior de contraste, a cascata do Cronograma Físico e as ocorrências das demais telas da amostra foram corrigidas nas declarações de origem. A varredura posterior de 80 páginas e o reteste das nove abas em 390 e 1865 px estão documentados no [relatório de testes](RELATORIO_TESTES_VISUAIS.md).
