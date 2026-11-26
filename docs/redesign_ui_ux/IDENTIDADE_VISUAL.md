# Identidade visual SAARI

| Elemento original | HEX | Origem |
| --- | --- | --- |
| Marrom institucional | `#453330` | Variável `--opal-blue-dark` no layout de entrada e `--saari-brown` no tema anterior |
| Marrom profundo | `#2D201C` | Layout e tema anterior |
| Bronze institucional | `#B9AA72` | Layout e tema anterior |
| Bege institucional | `#EEE8D6` | `--opal-blue-soft` no layout de entrada |
| Marrom do logotipo | `#503D2D` | [Logotipo original](../../static/img/saari/saari-logo-marrom.svg) |

O símbolo usado na navegação continua vindo de [saari-simbolo-gold.png](../../static/img/saari/saari-simbolo-gold.png). A tipografia usa Plus Jakarta Sans para trabalho e Source Serif 4 para títulos principais, com alternativas locais para ambas.

## Paleta adotada

| Papel | Claro | Escuro |
| --- | --- | --- |
| Fundo | `#F5F2ED` | `#1B1917` |
| Menu | `#32241F` | `#2C211E` |
| Card | `#FFFDFA` | `#24211E` |
| Superfície elevada | `#FFFFFF` | `#2E2925` |
| Campo | `#FFFDFA` | `#201D1B` |
| Borda geral | `#DED6CA` | `#494038` |
| Ação primária | `#453330` | `#88664F` |
| Link | `#745331` | `#D5B884` |
| Texto | `#352923` | `#F1E9DF` |
| Texto secundário | `#65564E` | `#C6B9AD` |

## Contraste dos tokens

| Par | Claro | Escuro |
| --- | ---: | ---: |
| Texto sobre fundo | 12,60:1 | 14,58:1 |
| Texto secundário sobre card | 6,91:1 | 8,35:1 |
| Link sobre card | 6,84:1 | 8,40:1 |
| Rótulo da ação primária sobre o botão | 11,43:1 | 4,98:1 |
| Texto do menu sobre o menu | 13,10:1 | 13,72:1 |
| Indicador de foco sobre campo | 5,69:1 | 8,79:1 |
| Borda de controle sobre campo | 3,39:1 | 4,08:1 |

As razões foram calculadas para pares sólidos definidos em [saari-tokens.css](../../static/css/saari-tokens.css), usando luminância relativa. O critério de referência é 4,5:1 para texto comum e 3:1 para controles e elementos não textuais relevantes. A leitura dos tokens complementa a verificação dos estilos efetivamente aplicados no navegador. [WCAG 2.2, W3C](https://www.w3.org/TR/WCAG22/)
