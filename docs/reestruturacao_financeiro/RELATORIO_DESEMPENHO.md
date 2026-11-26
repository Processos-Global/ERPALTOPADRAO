# Desempenho da reestruturação

Medição local em SQLite em memória, Python 3.13.18 e Django 6.0.7. As duas revisões receberam 1.500 títulos sintéticos de R$ 100,23, uma obra e um fornecedor, com vencimentos distribuídos em 91 dias, três estados em aberto e as origens disponíveis. O cliente Django usou um superusuário. Foram comparadas as medianas de sete `GET`s após aquecimento, incluindo SQL e renderização do template. Os dados abaixo foram coletados na mesma sessão, usando `94dc49c` e a árvore de trabalho.

| Tela | Consultas antes → depois | HTML antes → depois | Mediana antes → depois |
| --- | ---: | ---: | ---: |
| Visão Geral | 17 → 12 | 117.442 → 119.823 B | 185,61 → 26,11 ms |
| Contas a Pagar | 8 → 10 | 197.101 → 136.886 B | 114,70 → 19,26 ms |
| Agenda, próximos 30 dias | 9 → 10 | 132.451 → 137.037 B | 35,65 → 18,08 ms |
| Compromissos, sem pedidos na massa | 7 → 6 | 115.645 → 114.592 B | 19,16 → 22,55 ms |
| Planejamento Financeiro | 5 → 13 | 131.400 → 139.531 B | 245,16 → 38,98 ms |
| Indicadores, aba Geral | 29 → 13 | 148.214 → 118.084 B | 371,90 → 12,25 ms |

Contas a Pagar executa agregações de saldo no banco e reduz o HTML dos controles repetidos por título. A Visão Geral e Indicadores deixaram de consultar análises que pertencem a outras telas. Planejamento Financeiro usa fontes por etapa e pagina o conjunto no banco. Os novos filtros e os novos indicadores aumentaram o HTML da Visão Geral, Agenda e Planejamento Financeiro em relação ao baseline. A abertura de Compromissos ficou 3,39 ms mais lenta nesta massa sem pedidos.

Na medição anterior da solicitação avulsa, 300 fornecedores, 300 materiais, 25 obras e 35 apropriações produziram 305 → 0 consultas, 210.744 → 122.225 bytes e 168,2 → 13,2 ms em `RequestFactory`, com superusuário e shell equivalente. O dropdown assíncrono consulta no máximo 25 resultados por busca. Os números de Compras, Cadastros, Ficha Técnica e cronogramas estão no [relatório dos demais módulos](../melhorias_erp/RELATORIO_DESEMPENHO.md).

As medições não incluem rede, CDN, navegador, tempo de execução concorrente em produção ou desempenho do MySQL hospedado. Os testes MySQL confirmam comportamento, consultas seletivas e bloqueios dos cenários verificados.
