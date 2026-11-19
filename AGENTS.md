# SAARI ERP Alto Padrão — instruções permanentes

## Coordenação
A sessão principal do Codex coordena arquitetura, integração e entrega. Antes de cada etapa, leia o pedido vigente, o estado do Git e os arquivos envolvidos. Não antecipe escopo ou regras além do pedido vigente. Delegue partes independentes aos seis especialistas em .codex/agents/ quando útil; trabalhos pequenos podem ficar com o coordenador. Limite: três subagentes simultâneos. Mantenha relação de tarefa, agente, arquivos atribuídos e estado. Um arquivo tem um editor por vez; leituras podem ser paralelas. Agentes não delegam novamente sem coordenação.

Ao delegar, informe objetivo, evidências verificadas, arquivos permitidos, dependências, restrições, critérios de aceitação e testes. Use o agente nominal se o cliente permitir; caso contrário, transmita as instruções explicitamente e não presuma carregamento automático. Peça caminhos, linhas, resultados, fatos, hipóteses e bloqueios. Aguarde dependências, revise o diff conjunto e entregue uma conclusão única. Não reverta trabalho alheio; interrompa a edição afetada diante de alteração inesperada.

## Arquitetura verificada
- manage.py carrega config.settings; config/urls.py inclui core, usuarios, obras, orcamento, planejamento, suprimentos, compras, contratos, financeiro, almoxarifado, projetos, vistorias, diario_obra, pos_obra, relatorios, integracoes e cadastros.
- config/settings.py registra os apps, templates globais em templates/, middleware de isolamento do portal cliente em pos_obra, MySQL configurado por ambiente e mídias públicas/privadas. Nunca trate o banco padrão como descartável.
- Models, views, forms e services estão particionados em pacotes em vários apps. Localize definições, chamadas, sinais, URLs, permissões e testes antes de alterar contratos.
- A interface usa templates/layouts/base.html, templates/components/saari_theme.html, static/css/base.css e estilos específicos. templates/financeiro/base_financeiro.html herda a base global. Consulte herança, includes, JavaScript e cascata real.
- Pontos de integração observados: compras/services/integracao_planejamento.py, planejamento/services/cronograma_suprimentos/painel.py, financeiro/services/integracoes.py. Investigue cada fluxo antes de assumir sua semântica.
- requirements.txt declara Django 6.0.7, pandas, openpyxl, reportlab e pypdf. Há PDF em compras/services/ e pos_obra/relatorios.py, e planilhas em financeiro/views/relatorios.py. Confirme o ambiente ativo antes de executar Python.

## Invariantes
1. Não invente apps, models, campos, relações, estados ou políticas. Comprove regras em definições e consumidores; peça esclarecimento se faltar decisão de negócio.
2. Preserve comportamentos, permissões, URLs, contratos de templates e integrações. Para mudança transversal, mapeie produtores, consumidores, relatórios, importações e notificações.
3. Preserve identidade SAARI: componentes, cores, tipografia, espaçamento, navegação, acessibilidade, responsividade e temas claro/escuro.
4. Proteja autenticação, autorização por ação/objeto, isolamento de cliente/obra, CSRF, uploads, downloads e mídia privada. Não exponha segredos; não altere .env ou credenciais.
5. Não faça cargas, seeds, manutenção, migrações aplicadas, testes em produção ou deploy automático. Migração nova exige mudança de esquema demonstrada, plano para dados existentes, revisão de reversibilidade e validação isolada.
6. Para valores e indicadores, confirme origem, fórmula, unidade, período, filtros, precisão, arredondamento, nulos, duplicidade e estornos. Identifique fixtures sintéticas. Financeiro valida fórmulas antes de apresentação; QA verifica cenários.
7. Teste proporcionalmente. Antes de rodar Django, confirme configuração e destino do banco de teste isolado. Para apenas instruções/configuração, valide sintaxe e estrutura sem iniciar a aplicação ou acessar banco. Registre comandos, resultados e limites.
8. Restrinja edições ao escopo atribuído. Skills em .agents/skills/ não concedem autorização extra.

## Execução das etapas autorizadas
O prompt mestre de melhorias especifica oito etapas de implementação. Execute somente o escopo autorizado na conversa vigente, em ordem de dependência, com validação isolada após cada etapa. O coordenador identifica módulos e critérios, seleciona especialistas e skills pertinentes, atribui arquivos sem sobreposição e consolida revisão e validação. Especialistas: backend, frontend, financeiro, compras_almoxarifado, planejamento, qa_seguranca. O coordenador não é um sétimo agente. Modelos e esforço são herdados; instruções não mudam sandbox nem aprovações. Não faça commit, push ou implantação sem pedido explícito.
