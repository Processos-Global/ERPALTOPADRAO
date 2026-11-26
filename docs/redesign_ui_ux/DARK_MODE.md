# Tema claro, escuro e automático

[theme_init.html](../../templates/components/theme_init.html) resolve a preferência antes da pintura. A opção Automático acompanha `prefers-color-scheme`. O documento recebe `data-theme` e `data-bs-theme` com o modo efetivo. [saari-theme.js](../../static/js/saari-theme.js) atualiza os atributos, o seletor e a cor da interface do navegador. A preferência é compartilhada entre novas páginas e abas da mesma origem por `localStorage`, com leitura compatível da chave antiga de autenticação.

O ERP, o portal, o login, a recuperação de senha e a confirmação pública de Concretagem carregam o inicializador compartilhado. O evento `saari:themechange` informa o tema efetivo aos gráficos de Planejamento e Indicadores. Os gráficos de Concretagem também acompanham os atributos do documento.

O CSS distingue fundo, menu, card, campo e superfície elevada. Formulários pesquisáveis usam a mesma paleta em modais. Estilos de impressão ocultam a estrutura de navegação. As exportações geradas no servidor mantêm a formatação própria dos documentos.
