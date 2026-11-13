# Validação dos relatórios

## Ambiente e isolamento

Python `.venv` 3.14.4, Django 6.0.7, SQLite 3.50.4, confirmados por import direto. No subagente QA não havia ferramenta dedicada disponível; o coordenador configurou o ambiente via configurePythonEnvironment/getPythonExecutableCommand e confirmou .venv Python 3.14.4 antes da execução.

`relatorios/test_settings.py` é independente: não importa `config.settings`, não lê `.env`, declara somente alias `default`, engine SQLite e NAME/TEST.NAME `:memory:`. Asserções executam durante carregamento de settings, antes de django.setup. MIGRATION_MODULES desabilita migrações de todos os apps. O runner cria schema de teste efêmero e destrói a conexão ao fim; não foi executado comando migrate. Fixtures não salvam arquivos nem credenciais. O teste também verifica que config.settings não está carregado.

## Comandos reproduzíveis

```powershell
.venv/Scripts/python.exe --version
.venv/Scripts/python.exe -c "import django, sqlite3; print(django.get_version(), sqlite3.sqlite_version)"
.venv/Scripts/python.exe manage.py check --settings=relatorios.test_settings
.venv/Scripts/python.exe manage.py test relatorios --settings=relatorios.test_settings --verbosity=1 --noinput
```

## Baseline antes das correções

- check: nenhum problema, zero silenciados. Primeira tentativa identificou ausência de PRIVATE_MEDIA_ROOT nos settings de teste; adicionada configuração inerte, sem gravação.
- Primeira suíte: 13 testes, 11 falhas e 2 erros, 0,976s. Há subtests, portanto contagem de falhas não equivale a quantidade de métodos reprovados.
- Suíte ampliada: 17 testes, 15 falhas e 2 erros, 0,951s.
- Falhas confirmam ausência de saldo aberto (950/0/950), ação de visualização/exportação não verificada, usuário inativo aceito, IDs/datas inválidos ignorados, chart sem metadados, aging incorreto, cobertura incluindo reabertas, empreendimento sem OS descartado e comparação física arredondada prematuramente.
- Erros confirmam Unicode `²` em int e overflow no fim 9999-12-31.
- Sete páginas vazias renderizaram; CSV com permissão explícita e inversão de datas passaram.

## Dados sintéticos e expectativas independentes

- Financeiro em reais: 1000 original + 50 juros - 100 desconto = 950; pagamento singular integral efetivado de 950 resulta em zero; estornado preserva 950. Nenhuma regra de pagamento parcial introduzida.
- Aging: relógio fixo em 2026-11-11 12h local; sete OS com 30;30,5;31;60;61;90;91 dias resultam em 6/3/1 para duração estritamente superior a 30/60/90 períodos de 24 horas.
- Cobertura: duas OS concluídas com pesquisa e uma reaberta com pesquisa; numerador e denominador válidos são ambos 2, cobertura 100%.
- Físico: 49,96% executado contra 50,04% previsto ainda indica atrás antes de arredondar apresentação.

## Limitações

Baseline deliberadamente vermelho; não representa a validação final registrada abaixo. SQLite não comprova particularidades MySQL. Nenhum dado real foi usado. Nenhum arquivo de aplicação foi alterado pelo QA.


## Ampliação após baseline

Suíte ampliada para 20 testes com saldo negativo limitado a zero, CSV contra fórmulas e snapshot as-of. Guarda adicional na importação do módulo exige settings independentes e SQLite memória antes de setup_databases. Execução durante implementação concorrente: 20 testes, 10 falhas e 15 erros (subtests), 1,255s; não é baseline estável nem validação final. Reexecutar quando backend e frontend concluírem. Cenários CSV e snapshots agora estão implementados; ainda faltam FVS/economia/JS e revisão final.

## Validação final pelo coordenador — 2026-11-11

- `manage.py test relatorios --settings=relatorios.test_settings --verbosity=1 --noinput`: **27 testes, OK, 1,088s**. Python 3.14.4 / Django 6.0.7 da venv do projeto.
- `manage.py check --settings=relatorios.test_settings`: nenhum problema, zero silenciados.
- SQLite em memória exclusivamente; settings independentes não importam config.settings, não carregam .env e desabilitam migrações. Criação/destruição apenas do banco de teste em memória pelo runner; nenhuma migração executada.
- Cobertura adicional: FVS C/(C+NC) e isolamento por obra; vencidos líquidos e vencimento nulo; meses locais e meses intermediários vazios; contratos de gráficos das sete páginas; componente sem BOM que gerava item anônimo na grade.
- Diagnósticos do editor: nenhum erro em relatorios/ e static/relatorios/. `git diff --check`: passou; avisos apenas sobre conversão futura LF/CRLF.
- Prévia temporária do template real com contexto sintético, servida em localhost, sem consultas ao banco. ECharts 6.1.0 inicializou barras negativas, barras com duas séries e pontos de satisfação com valor nulo. Alternância gráfico/tabela funcionou. Grade corrigida para duas colunas no desktop; largura móvel estabilizada sem transbordamento da página. Temas e impressão ainda exigem conferência visual completa local.
- `node --check` não executou: Node não está no PATH. O JavaScript real foi carregado e executado pelo navegador; isso não equivale a uma suíte automatizada de JS.
- Agente QA produziu estratégia, banco isolado e testes de regressão. Após um impedimento temporário por limite de uso, concluiu a revisão final somente leitura sem bloqueador adicional comprovado. O coordenador incorporou a precisão da metodologia de aging, caso 30 dias e 12 horas e caso financeiro consistente PAGO.

## Pendências de homologação

1. Conferir sete páginas com dados representativos, permissões de usuários reais, exportação, impressão, temas e telas pequenas.
2. Executar em banco de homologação isolado do mesmo motor usado no ambiente real; medir tempo/consultas com grandes volumes. Não executar esta suíte com settings da aplicação.
3. Reconciliar amostras financeiras, descontos de cotação e datas com responsáveis do negócio. Economia exibida é explicitamente bruta; não é economia líquida de descontos/frete.
4. Acrescentar regressões específicas para adjudicações com descontos, fornecedores homônimos, marcos duplicados e testes de navegador completos; não foram cobertas integralmente nesta suíte.
5. Custo de materiais não é custo total, repetição textual é indício de reincidência, e evolução física depende dos snapshots existentes. Não há dados para criar custos completos ou erro histórico de previsão com segurança.

## Reprodução local segura (PowerShell, raiz do projeto)

```powershell
& .\.venv\Scripts\python.exe manage.py check --settings=relatorios.test_settings
& .\.venv\Scripts\python.exe manage.py test relatorios --settings=relatorios.test_settings --verbosity=2 --noinput
```

Não foram realizados commit, push, deploy, alterações de credenciais ou escrita em banco de aplicação.
