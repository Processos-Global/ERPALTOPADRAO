# Implementação frontend de relatórios

Data: 2026-11-11. Perfil frontend e instruções locais lidos. Escopo exclusivo: templates/relatorios e static/relatorios; este registro autorizado pelo coordenador.

## Mudanças

- Template principal preserva navegação horizontal, filtros GET, CSV condicionado a pode_exportar, impressão e identidade SAARI. Cards mostram atenção apenas por severity explícita; base em detalhe expansível usa subtitle existente.
- Componente _panel.html reutiliza estrutura e emite o painel por json_script. Tabela permanece visível sem JavaScript/CDN e suporta rows.series_values para comparações sem cálculo no cliente. Caption metodológica expansível.
- CSS e JavaScript extraídos para static/relatorios. Compactação local, sem primeiro painel automaticamente largo; contraste da aba ativa escura corrigido. CSS global não alterado.
- JS consome raw e chart; não converte texto formatado, não infere tipo pelo título/quantidade, não calcula indicador. Modos somente allowed_types. null é ausência; sinal não é removido. Contratos inválidos ou valores fora de limites mantêm tabela e aviso. Séries agrupadas, legendas, unidades, tooltip com todas as séries e linhas sem suavização/ligação de ausências.
- Escala vem do produtor (percent 0–100; score 1–5); referência zero para p.p. Sem teto artificial para dias/rate. Ordenação manual afeta apenas tabela; séries mantêm ordem recebida.
- ECharts 6.1.0 preservado; URL HTTPS corrigida. PNG, resize e atualização de tema mantidos. Impressão usa tabela, inclusive se gráfico indisponível, e abre detalhes temporariamente.

## Verificações reais

- `C:/Users/Global/AppData/Local/OpenAI/Codex/runtimes/cua_node/76f5b5935a63c7ba/bin/node.exe --check static/relatorios/painel.js`: exit 0.
- Leituras e pesquisas locais verificaram herança base.css → overrides base.html → extra_css → components/saari_theme.html; nenhum Bootstrap carregado nos templates examinados. Não foi instalado framework.
- Não houve acesso a banco, .env, credenciais, commit ou deploy.

## Limitações

Compilação/renderização Django, navegador, CDN real, foco/teclado, contraste medido e impressão real dependem da validação consolidada do coordenador/QA. Dados de produção não foram usados. A validação sintática JS não substitui validação visual. Backend deve fornecer todos os metadados e series_values alinhados, e restringir modos nominais a bar.
