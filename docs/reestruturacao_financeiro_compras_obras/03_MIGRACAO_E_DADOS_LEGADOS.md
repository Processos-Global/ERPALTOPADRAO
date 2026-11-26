# Migração e dados legados

## Reservas e cobertura

A fase de Compras e Almoxarifado mantém o esquema. Reservas consumidas, liberadas e ativas permanecem no histórico. O fluxo atual usa exclusivamente quantidades físicas nos movimentos e a quantidade comercial no processo de compra. A consulta histórica mantém os dados da reserva original mesmo quando o material da necessidade mudou. Casos bloqueados pela regra anterior antes da criação do processo não possuem registro que permita reconstrução.

`python manage.py diagnosticar_reservas_compra` lista reservas, estágio do processo, movimentos vinculados e contagens de pedidos por situação. O comando classifica a cobertura pelo valor originalmente reservado em relação à quantidade solicitada registrada. A saída padrão pode ser guardada como relatório. A opção `--aplicar` bloqueia as linhas legadas e libera apenas o saldo lógico de reservas ativas, em transação. A aplicação é idempotente. Movimentos e quantidades de Compras preservam os valores armazenados.

A execução com dados legados depende de homologação em cópia autorizada. Nesta implementação, o comando foi exercitado apenas com fixtures sintéticas. O fluxo operacional dispensa a regularização para entrar em uso.

## Recebimentos e obrigações

`compras.0044_solicitacoes_recebimentos` acrescenta o vencimento fiscal opcional. `financeiro.0017_solicitacoes_recebimentos` acrescenta valor esperado e divergências comerciais, registra o estado de correção, mantém a coluna de referência ao recebimento e permite títulos por parcela com unicidade de recebimento e ordem. As migrações preservam os vínculos e valores dos títulos existentes. As validações incluem reaplicação e reversão em SQLite com dados sintéticos e um título legado vinculado à entrega.

Após criar mais de um título para um recebimento, a unicidade antiga de um título por entrega deixou de expressar os dados. A reversão da migration financeira recusa essa situação antes de alterar o esquema. A recuperação depois de novas operações deve preservar títulos, relações, documentos e pagamentos posteriores à publicação.

`python manage.py diagnosticar_recebimentos_financeiros` lista vínculos entre pedidos, recebimentos, liberações e títulos. Os parâmetros `--pedido` e `--somente-pendencias` restringem a análise. A geração ocorre nos novos recebimentos pelo fluxo normal. A equipe pode corrigir documentação pendente no pedido ou reavaliá-la com permissão financeira. Vínculos legados aptos a gerar dupla obrigação exigem conciliação explícita. Títulos antigos em aprovação, aprovados ou pagos seguem com seus números e decisões. Prévias legadas aptas são canceladas com auditoria quando a obrigação legítima do recebimento é criada.

## Fotos do Diário de Obra

A correção incremental não altera o schema nem move arquivos históricos. Novos uploads são gravados usando `PrivateMediaStorage`, com prefixo `obras/diarios_privados/`, diretório por data e identificador exclusivo. O campo `arquivo` existente guarda o caminho; o serviço resolve explicitamente o storage correto nas três variantes. Se um arquivo privado estiver ausente, não há fallback para o storage público. Arquivos históricos mantêm sua localização original.

A transação e a compensação de arquivos removem os novos uploads conhecidos quando a gravação falha ou sofre rollback. Se a própria exclusão do storage falhar, o erro é registrado para análise; não existe garantia de limpeza física diante de falha simultânea de armazenamento ou interrupção abrupta do processo. Não criar mecanismo de exclusão remota automática.

As fotos históricas que foram publicadas no namespace público continuam potencialmente acessíveis por URLs antigas. Uma eventual migração de privacidade retroativa deve ser separada, inventariada, autorizada e testada, incluindo as cópias remotas e o servidor web. Após iniciar novos uploads privados, uma reversão para o código anterior ao patch deixaria essas fotos sem leitura pelas rotas antigas: preserve o resolvedor dos dois storages ou restaure uma versão compatível, sem tornar os arquivos públicos.
