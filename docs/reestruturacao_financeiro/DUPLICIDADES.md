# Duplicidades e idempotência

O POST anterior podia repetir a criação inteira depois de um duplo envio, de uma tentativa simultânea ou da perda da resposta HTTP. A solicitação passou a ter token assinado por usuário, impressão digital dos dados submetidos e dos anexos, e restrição única por usuário e chave. A transação inclui parcelas, histórico, anexos registrados e a notificação interna. Repetir o mesmo conteúdo volta ao mesmo título ou lote. A reutilização da chave com conteúdo diferente recebe HTTP 409. Um formulário novo gera outra chave e permite uma nova solicitação com os mesmos dados comerciais.

- A numeração FIN bloqueia a sequência do ano, verifica códigos já ocupados e preserva os números históricos. A decisão de aprovação bloqueia o título e usa o ciclo vigente. A emissão do pacote verifica o ciclo e a existência de outro item para o mesmo título sob o bloqueio do título.
- As notificações de aprovação criam registros internos pelo serviço de Usuários. A regra de destinatários respeita a permissão granular ativa. O fluxo atual não agenda e-mail ou outra chamada externa. Qualquer futura integração externa deve ser programada após o commit.
- Em caso de erro durante a anexação, o banco reverte a tentativa e o serviço tenta remover os arquivos que gravou. Uma interrupção abrupta do processo ainda pode deixar um arquivo físico órfão. A reversão da 0015 remove a chave e o vínculo técnico, preservando os títulos.

```bash
python manage.py diagnosticar_duplicidades_financeiras --saida duplicidades_financeiras.csv
```

O comando apenas lê o banco. O CSV apresenta classificação, registros relacionados e critérios usados. Uma proximidade de dez minutos e informações comerciais parecidas são evidências para conferência. Confirmação técnica exige vínculo ou evidência do mesmo grupo de origem e posição de parcela. O comando não cancela, exclui ou mescla títulos. Preserve o arquivo sob o mesmo controle de acesso dos dados financeiros.
