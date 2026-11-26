# Auditoria visual do SAARI ERP

A linha de base foi capturada a partir da árvore de trabalho de entrada, que já continha as alterações locais da reestruturação anterior. O Django renderizou as páginas com dados sintéticos em SQLite em memória. O Edge abriu o HTML e os arquivos estáticos dessa versão, congelados antes das alterações.

| Área | Diagnóstico |
| --- | --- |
| Identidade | O logotipo marrom e o símbolo bronze conviviam com declarações legadas em verde-petróleo no CSS da base. A ordem da cascata ainda permitia que essas declarações afetassem botões e foco. |
| Navegação | A barra lateral mostrava links de entrada por módulo. Havia CSS e JavaScript para submenus, sem o markup correspondente nas categorias internas. A barra superior tinha um espaço vazio para contexto. |
| Tema | O ERP e as páginas de autenticação mantinham inicializadores próprios. O tema geral tinha várias versões sobrepostas de superfícies escuras e regras fortes para corrigir componentes locais. |
| Página inicial | Cada módulo ocupava um card alto, com numeração, etiqueta e texto repetindo a função declarada no título. O painel exigia rolagem antes de mostrar todos os destinos em um notebook. |
| Financeiro e Compras | Algumas telas mantinham filtros na URL, mas os links de detalhe e de volta podiam perder a consulta. As páginas de títulos e pedidos usavam controles de seleção diferentes. |
| Planejamento e Indicadores | Chart.js e ECharts selecionavam cores por mecanismos diferentes. O tema de eixos, séries, legendas e tooltip precisava acompanhar a alternância feita na mesma página. |
| Obras e Projetos | Foram observados fundos fixos, estilos locais duplicados e controles de campo pouco adaptados ao toque. No relatório operacional inicial, FVS detalhe e duas telas de Concretagem extrapolavam o viewport. |
| Pós-Obra, Cadastros e Usuários | O Pós-Obra tinha uma camada que forçava tema claro em componentes internos. Campos, tabelas e cabeçalhos de Cadastros repetiam estilos locais. Login e recuperação usavam alternância binária própria. |

A matriz geral anterior examinou 31 páginas em cinco larguras e dois temas, totalizando 310 combinações. Essa matriz registrou zero erros de JavaScript e de rede e zero overflow no documento. A matriz operacional complementar examinou 27 rotas realistas, incluindo detalhes de FVS, Diário, Cautelar e Concretagem que não estavam na matriz geral inicial. Ela registrou dez casos de overflow em 270 combinações.

Consulte [capturas anteriores](evidencias/antes/), [matriz inicial](evidencias/matriz-antes.json) e [evidências operacionais](evidencias/operacional/).
