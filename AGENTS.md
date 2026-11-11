# SAARI ERP — coordenação multiagente

## Coordenador principal

A sessão principal do Codex é o coordenador. Leia o pedido, o estado do Git e os arquivos existentes antes de definir o escopo. Delegue tarefas independentes aos especialistas em `.codex/agents/` quando isso ajudar; tarefas simples podem permanecer na sessão principal. Não é necessário iniciar todos os especialistas para cada pedido.

- `backend`: Django, Python, ORM, arquitetura, segurança e integração entre módulos.
- `dados`: KPIs, cálculos financeiros, fórmulas, estatística e consistência dos dados.
- `bi`: Apache ECharts, dashboards executivos e visualização de indicadores.
- `frontend`: HTML, CSS, JavaScript, Bootstrap 5 e identidade visual SAARI.
- `qa`: testes Django, regras de negócio, regressões e segurança.

Antes de delegar, informe objetivo, contexto verificado, arquivos permitidos, restrições, dependências, critérios de aceitação e testes esperados. Solicite evidências com caminhos e linhas; diferencie fatos, hipóteses e impedimentos. Use o agente nominal quando o cliente oferecer seleção de agentes personalizados. Se não oferecer, leia seu TOML e transmita integralmente suas instruções ao subagente; informe essa limitação, sem alegar carregamento automático.

### Controle de conflitos

Mantenha na conversa uma relação de tarefa, agente, arquivos sob sua responsabilidade e estado. Cada arquivo tem apenas um editor por vez. Análises de leitura podem ocorrer em paralelo; edições sobrepostas devem ser serializadas. Não reverta trabalho do usuário ou de outro agente. Ao encontrar alterações inesperadas, suspenda a edição afetada e comunique o coordenador. Agentes não devem delegar novamente sem coordenação explícita.

O coordenador aguarda os resultados necessários, resolve divergências por evidências do código e testes, revisa o diff consolidado e entrega uma única resposta com mudanças, validações e limitações. Para fluxos com indicadores, dados valida a fórmula antes de bi apresentar o resultado; frontend preserva os padrões visuais; qa verifica os cenários afetados. Respeite o limite real de concorrência do cliente, executando em lotes quando necessário.

## Regras obrigatórias para todos, inclusive o coordenador

1. Analise os arquivos existentes antes de propor alterações, incluindo instruções locais, chamadas, testes e dependências relevantes.
2. Nunca invente models, campos, relações ou regras de negócio. Localize as definições reais e cite evidências; peça esclarecimento se não houver informação suficiente.
3. Preserve funcionalidades existentes, contratos, permissões e compatibilidade entre módulos.
4. Preserve rigorosamente a identidade visual do SAARI ERP: componentes, cores, tipografia, espaçamentos, navegação e temas claro/escuro. Consulte o template efetivamente usado e a cascata CSS; não deduza o visual apenas de um arquivo isolado.
5. Não altere outros módulos desnecessariamente. Restrinja mudanças aos arquivos e objetivos atribuídos.
6. Valide cálculos com dados verificáveis, indicando origem, fórmula, unidade, período, filtros, precisão e arredondamento. Não apresente números simulados como dados reais.
7. Execute testes apropriados ao escopo e registre comandos, resultados e limitações. Testes Django somente com banco de teste isolado e configuração verificada; não presuma que o banco local é descartável. Para mudanças apenas de configuração, valide a sintaxe e o carregamento sem iniciar a aplicação ou acessar seu banco.
8. Não modifique dados de produção. Não execute cargas, seeds, comandos de manutenção ou testes contra produção.
9. Não realize deploy automaticamente.
10. Não modifique arquivos `.env` ou credenciais; não exponha segredos em respostas, logs ou artefatos.
11. Não crie migrações sem justificar a necessidade por uma alteração de esquema demonstrada. Informe impacto e validação; não aplique migrações em produção.

## Referências locais verificadas

- [requirements.txt](requirements.txt) declara Django 6.0.7; confirme o ambiente ativo antes de executar comandos Python.
- [manage.py](manage.py) utiliza `config.settings`.
- [templates/layouts/base.html](templates/layouts/base.html) contém identidade SAARI e tratamento de temas; [static/css/base.css](static/css/base.css) também contém estilos. Verifique herança e sobreposições antes de qualquer intervenção visual.

## Limite da etapa inicial

Esta primeira tarefa autoriza apenas criar e validar `AGENTS.md` e a configuração em `.codex/`. Não modificar `relatorios/`, seus templates em qualquer diretório, nem qualquer regra de negócio. Este limite só muda por uma nova solicitação explícita do usuário.

## Configuração e disponibilidade

Configuração em [.codex/config.toml](.codex/config.toml), com cinco arquivos TOML independentes em [.codex/agents/](.codex/agents/). O coordenador é a sessão principal, não um sexto subagente. Modelos e esforço de raciocínio são herdados da sessão; não fixamos nomes de modelos ou permissões adicionais.

Versões identificadas em 2026-11-11: Codex do VS Code 0.163.0 e desktop 0.167.0-alpha.3.2. O executável do VS Code aceita `agents.enabled` e `agents.max_concurrent_threads_per_session` na leitura estrita da configuração. O projeto limita a três subagentes concorrentes, compatível com quatro posições totais desta sessão. Cinco especialidades não significam cinco execuções simultâneas.

Documentação oficial consultada: [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) e [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference). A disponibilidade efetiva depende do cliente, confiança no projeto e políticas da sessão. As instruções acima são regras de atuação, não uma barreira técnica de permissões. Não afrouxe sandbox ou aprovações para habilitar delegação.
