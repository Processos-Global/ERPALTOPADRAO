# Testes visuais e funcionais

## Ambiente

Edge 158.0.4370.33 com Playwright, usando HTML produzido pelo Django com dados sintéticos e arquivos estáticos locais. O navegador reproduziu o HTML, as respostas assíncronas e os downloads gerados pelas views. Os testes Django executaram permissões, CSRF e operações de gravação em bancos descartáveis. Python 3.13.18 e Django 6.0.7 foram usados na aplicação.

## Matriz geral

| Rodada | Páginas | Larguras | Temas | Verificações | Erros de JavaScript ou rede | Overflow no documento |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Antes | 31 | 5 | 2 | 310 | 0 | 0 |
| Depois | 36 | 5 | 2 | 360 | 0 | 0 |

Larguras em CSS px de 1920, 1366, 1280, 768 e 390. A matriz posterior também inclui o menu de Compras, a lista de pedidos, a lista de processos, o quadro de Pós-Obra e o login. [Matriz anterior](evidencias/matriz-antes.json) · [Matriz posterior](evidencias/matriz-depois.json)

| Matriz complementar | Antes | Depois | Resultado posterior |
| --- | ---: | ---: | --- |
| Obras, Concretagem, FVS, Vistorias, Projetos e Orçamento | 270 | 290 | Zero erros de JavaScript. A matriz encontrou quatro casos de overflow em FVS nas larguras 768 e 1280 px. O reteste de FVS confirmou zero overflow nas dez combinações. |
| Login, Portal, Pós-Obra, Cadastros e Usuários | 160 | 160 | Zero erros de JavaScript ou de rede e zero overflow. |

[Matriz operacional inicial](evidencias/operacional/before-matriz.json) · [Matriz operacional posterior](evidencias/operacional/after-matriz.json) · [Reteste de FVS](evidencias/operacional/fvs-reteste.json) · [Matriz de Portal e Cadastros](evidencias/portal-cadastros/evidencias/matriz-depois.json)

## Comparações visuais

| Tela | Antes | Depois |
| --- | --- | --- |
| Painel geral em 1366 px, escuro | [Antes](evidencias/antes/Inicio-dark-1366.png) | [Depois](evidencias/depois/Inicio-dark-1366.png) |
| Financeiro em 1366 px, claro | [Antes](evidencias/antes/Financeiro-Visao-Geral-light-1366.png) | [Depois](evidencias/depois/Financeiro-Visao-Geral-light-1366.png) |
| Solicitação financeira em 390 px, escuro | [Antes](evidencias/antes/Financeiro-Solicitacao-dark-390.png) | [Depois](evidencias/depois/Financeiro-Solicitacao-dark-390.png) |
| Curva S em 1366 px, escuro | [Antes](evidencias/antes/Cronograma-Fisico-dark-1366.png) | [Depois](evidencias/depois/Cronograma-Fisico-dark-1366.png) |
| Diário de Obra em 390 px, claro | [Antes](evidencias/antes/Diario-Obra-light-390.png) | [Depois](evidencias/depois/Diario-Obra-light-390.png) |
| FVS detalhe em 390 px, claro | [Antes](evidencias/operacional/before-fvs-detalhe-light-390.png) | [Depois](evidencias/operacional/after-fvs-detalhe-light-390.png) |
| Portal do Cliente em 390 px, escuro | [Antes](evidencias/antes/Pos-Obra-Portal-dark-390.png) | [Depois](evidencias/depois/Pos-Obra-Portal-dark-390.png) |

As pastas [antes](evidencias/antes/) e [depois](evidencias/depois/) incluem outras combinações, com as cinco larguras disponíveis para a home. As pastas [operacional](evidencias/operacional/) e [portal e cadastros](evidencias/portal-cadastros/) reúnem as matrizes específicas.

## Interações e acessibilidade

O roteiro geral aprovou dez fluxos, incluindo menu, foco, Ctrl+K e Command+K, busca por texto com e sem acentos, favoritos, recentes, breadcrumbs, estados de tema entre abas, retorno ao Financeiro com filtros, atualização da Curva S e downloads de PDF, XLSX e CSV. [Interações globais](evidencias/interacoes-globais.json)

Portal, Pós-Obra e Cadastros acrescentaram oito interações aprovadas, incluindo exibição de senha, alternância de tema, consulta mantida ao voltar da OS, aba Documentos no celular e pesquisa por responsável por teclado. [Interações de Portal e Cadastros](evidencias/portal-cadastros/evidencias/interacoes.json)

Em Concretagem, as setas alteraram a aba selecionada. A seleção persistiu após atualizar. O modal de caminhão abriu com foco no botão de fechar, confinou Tab e Shift+Tab e devolveu o foco ao botão de origem ao pressionar Escape. O fluxo foi repetido nos dois temas em 390 px. [Interações de Concretagem](evidencias/operacional/interacoes.json) · [Modal no escuro](evidencias/operacional/after-concretagem-modal-dark-390.png)

Os 16 pares de cor renderizados medidos em títulos, menu ativo, botão primário e campo de senha variaram de 6,78:1 a 14:1, acima de 4,5:1. Os pares de tokens estão na [identidade visual](IDENTIDADE_VISUAL.md). A verificação automatizada cobre os cenários registrados e a homologação inclui leitores de tela e dispositivos físicos. [Contraste renderizado no Edge](evidencias/contraste-renderizado.json)

## Comandos

```powershell
$python = '.venv/Scripts/python.exe'
$mysqld = 'C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqld.exe'
& $python manage.py check --settings=relatorios.test_settings
& $python manage.py test --settings=relatorios.test_settings --verbosity 1 --noinput
& $python -m relatorios.executar_mysql_qa --mysqld $mysqld --com-migrations makemigrations --check --dry-run
& $python -m relatorios.executar_mysql_qa --mysqld $mysqld --com-migrations test --verbosity 1 --noinput
```

O perfil SQLite executou 467 testes, com 465 aprovados e duas omissões nos cenários que exigem bloqueio por `SELECT FOR UPDATE`. O system check SQLite ficou limpo. O MySQL descartável 8.0.46 aprovou os 467 testes com migrations reais, 0 falhas e 0 omissões. O comando de verificação de migrations exibiu `No changes detected`. O aviso preexistente `mysql.W003` permanece. Houve também 207 templates compilados, com zero erros.

## Transferência de HTML

Nas 31 páginas comuns renderizadas com as mesmas fixtures, a mediana do HTML sem compressão caiu de 120.051 para 67.141 bytes, efeito da extração de CSS e JavaScript compartilhados. A home passou de 108.580 para 45.913 bytes. O Financeiro passou de 122.386 para 70.832 bytes. Esses valores medem o corpo HTML das respostas. O tamanho total transferido também depende dos estáticos e do cache, e a medição não inclui latência de produção. [Dados por página](evidencias/desempenho-html.json)

O `STATIC_ROOT` local foi confirmado em `C:/Dev/ERPALTOPADRAO/staticfiles`. O comando `collectstatic --clear --noinput` usou as pastas de origem e destino definidas pela aplicação em um perfil isolado. Foram recolhidos 177 arquivos e verificados oito hashes.

## Revisão de contraste após o redesign

O Cronograma Físico tinha duas declarações locais de `--pc-card`. A segunda fixava uma superfície branca em ambos os temas. Regras do mesmo template também fixavam o marrom escuro nos percentuais e na aba ativa. As superfícies e o texto passaram a consumir os tokens semânticos da SAARI. As barras de progresso usam as mesmas cores de série da Curva S.

| Elemento no tema escuro | Antes | Depois |
| --- | ---: | ---: |
| Percentuais de Previsto e Realizado | 1,02:1 | 13,32:1 |
| Botão Histórico | 1,06:1 | 11,96:1 |
| Rótulos de Obra e Semana | 1,85:1 | 7,99:1 |
| Aba ativa | 1,35:1 | 7,01:1 |

[Cronograma antes](evidencias/contraste/cronograma-antes-dark-1865.png) · [Cronograma depois](evidencias/contraste/cronograma-contraste-depois-dark-1865.png) · [Modo escuro em 390 px](evidencias/contraste/cronograma-contraste-depois-dark-390.png)

A varredura inicial de 70 páginas renderizadas no escuro encontrou 20 combinações de texto abaixo do limiar de contraste e 16 superfícies claras, contadas por combinação de componente e cor em cada página. A revisão corrigiu ocorrências em Suprimentos, Ficha Técnica, Compras, Contratos, Almoxarifado, Liberações de Pós-Obra, Indicadores e Usuários. A nova varredura de 80 páginas retornou zero ocorrências segundo os critérios da amostra. O reteste incluiu as nove abas do Cronograma Físico nos dois temas em 390 e 1865 px.

O roteiro mediu texto visível em fundos sólidos pela cor computada, incluindo a composição das camadas translúcidas. Também sinalizou superfícies claras no escuro e gradientes com todos os pontos de cor claros. As medições usam dados sintéticos. [Medições iniciais](evidencias/contraste/medicoes-antes.json) · [Varredura posterior](evidencias/contraste/medicoes-contraste-depois.json) · [Cronograma em 1865 px](evidencias/contraste/medicoes-contraste-depois1865.json) · [Cronograma em 390 px](evidencias/contraste/medicoes-contraste-depois390.json)

O teste de interação alternou de Escuro para Claro e voltou para Escuro na mesma página. Repetiu a medição dos rótulos, da aba ativa, dos percentuais e do botão Histórico com foco e ponteiro. A suíte SQLite executou 467 testes, com 465 aprovados e as duas omissões esperadas para bloqueios de banco. A coleta local atualizou as folhas de estilo e conferiu os hashes das cópias. [Alternância de tema e foco](evidencias/contraste/interacao-cronograma.json)

Suprimentos, Contratos, Estoque e Liberações de Pós-Obra somaram 116 medições em 24 combinações de tela, largura e tema. Houve 54 falhas identificadas antes dos ajustes e zero no reteste. Os modais de saída e transferência do Almoxarifado passaram em oito combinações, com contraste mínimo de 4,98:1 entre os 48 pares medidos. A seleção por teclado manteve o foco visível dentro da lista. [Medições complementares](evidencias/contraste/depois-contrast-depois.json) · [Modais do Almoxarifado](evidencias/contraste/modais-almoxarifado.json)
