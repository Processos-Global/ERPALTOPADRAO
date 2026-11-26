# Progresso da reestruturação

## 25/11/2026 — Conferência da árvore após a interrupção

- A retomada encontrou `main` em `4f4bbda`, alinhada com a referência local `origin/main`, com 33 arquivos modificados e 26 novos. O inventário e as evidências a seguir descrevem o trabalho que já estava na árvore. As correções manuais de compatibilidade estão no commit.
- A configuração original de Concretagem passou novamente com 102 testes em SQLite. A suíte ampliada com `test . financeiro/tests` encontrou 452 casos, dos quais 450 passaram e dois dependem de bloqueio de linha. `check` SQLite passou. `check --database default`, `makemigrations --check --dry-run` e `migrate --plan --noinput` no MySQL descartável confirmaram somente `mysql.W003`, nenhuma divergência de models e plano válido.
- A matriz do Edge e os seis arquivos exportados estão presentes na pasta temporária registrada no relatório. A revisão dos pontos de entrada das exportações identificou células textuais interpretadas como fórmulas e um indicador local que permanece ativo no POST de download de transferências. A abertura de notificações também grava por GET. Próxima etapa desta conferência é testar e corrigir esses fluxos antes de repetir as suítes.

## 25/11/2026 — Retomada e Concretagem

- Ponto de partida `4f4bbda` na branch `main`, sem diferenças locais ou arquivos novos. O diff `94dc49c..4f4bbda` contém 161 arquivos, incluindo as correções manuais dos testes de Ficha Técnica, Projetos, Compras e Planejamento Financeiro. As quatro migrations da rodada anterior já constam na revisão.
- Resultado informado na retomada: 99 testes em MySQL e aplicação das migrations em banco temporário, após carregar as tabelas de fusos horários. Essa evidência pertence à execução anterior.
- Execução própria `manage.py test obras.tests_concretagem obras.tests_concretagem_execucao obras.tests_concretagem_mapa --settings=obras.test_settings_concretagem --verbosity 1` em Python 3.13.18: 102 aprovados em SQLite em memória. A mensagem de falha do Drive é produzida pelo caso que simula indisponibilidade.
- A guarda comum da Concretagem aceitava apenas SQLite. A suíte de Relatórios verificava o módulo e o banco na coleta. O perfil MySQL descartável exige nome e conta de QA exclusivos e preserva e-mail em memória, mídia temporária e Drive desativado.

## Unicidade e revisão financeira

- Migrations `cadastros/0017`–`0018` criam a chave gerada para documento preenchido. As migrations `compras/0042`–`0043` criam unicidade por processo e fornecedor para contratações ativas. Os diagnósticos correspondentes fazem somente leituras e as migrations recusam históricos incompatíveis. O índice completo de Suprimentos permaneceu com 500 caracteres e foi exercitado no MySQL descartável.
- O executor MySQL usa processo isolado, conta exclusiva e conversões por nome em `UTC` e `America/Sao_Paulo`. Os 146 testes focados iniciais passaram, inclusive Concretagem. A etapa de migrations reais aplicou também as quatro migrations novas. A execução de Planejamento Financeiro após preparar os dois fusos passou com 5 testes.
- A Visão Geral agora mantém obra, fornecedor, classe, apropriação e origem na agenda, nos indicadores e nos atalhos. Pagos usam a data efetiva. O financeiro conservou a arquitetura de parcelas, programação, estorno e frete. Foram corrigidos destinatários sem aprovação, proteção do CSV de frete e anexos com mesmo nome e tamanho e conteúdo diferente.
- O teste de concorrência de estoque validou duas transações MySQL sobre a mesma obra e material. Os 13 testes de cobertura passaram, com uma única reserva para o saldo existente.
- A validação Edge encontrou e reproduziu problemas de foco do histórico, ícone de tema, responsividade e contraste no escuro. Os relatórios registram as capturas, os fluxos reproduzidos e as limitações.

## Validação final e entrega

- A revisão de QA antecipou a guarda de Concretagem para a coleta em `obras/tests_concretagem.py`. `relatorios/executar_mysql_qa.py` passou a fixar o perfil Django no processo filho, recusar opções que substituem configurações ou caminho de importação e exigir validação sem gravação em `makemigrations`. Os três testes da guarda passaram junto dos 102 de Concretagem no SQLite.
- A suíte completa passou com 447 testes em MySQL descartável com migrations reais e 445 aprovados em SQLite. Os dois casos de concorrência dependentes de bloqueio de linha foram executados no MySQL. As duas adequações de testes estão em `compras/test_sla.py` e `pos_obra/test_ui.py`. Os 105 testes focados de Financeiro, Ficha Técnica, Projetos e Compras passaram em SQLite. [Resultados por módulo e comandos](RELATORIO_TESTES.md)
- `check`, `makemigrations --check --dry-run` e `migrate --plan` passaram nos perfis isolados. O MySQL manteve o aviso `mysql.W003`, documentado e validado com o índice completo de Suprimentos. Nenhum dado persistente foi consultado ou modificado.
- O Edge validou 31 páginas em 186 combinações, 20 interações e seis downloads. O benchmark comparou a revisão `94dc49c` com a entrega usando 1.500 títulos sintéticos em SQLite. Os relatórios registram contrastes, telas, consultas, tamanhos e tempos medidos. [Testes](RELATORIO_TESTES.md) · [Desempenho](RELATORIO_DESEMPENHO.md)
- Os dez documentos financeiros foram concluídos e os documentos gerais passaram a referenciar o escopo integrado. O inventário por área está no [relatório de implementação](RELATORIO_IMPLEMENTACAO.md).

## Pendências de negócio e próxima etapa

O estorno de Grande Fornecedor precisa de uma regra para restaurar o estado da parcela de Compras. Frete devido a transportadora distinta, pagamentos parciais em um único título e atribuição de obras a usuários internos também aguardam definição. A próxima etapa é a homologação operacional autorizada em cópia isolada. Confirme `CONVERT_TZ` com as duas datas de referência, inspecione o índice de Suprimentos e execute os dois diagnósticos de unicidade antes de aplicar as migrations. [Checklist](CHECKLIST_VALIDACAO.md) · [Backup, recuperação e publicação](INSTRUCOES_DEPLOY.md)
