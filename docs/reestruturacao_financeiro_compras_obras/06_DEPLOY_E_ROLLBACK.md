# Atualização e recuperação no PythonAnywhere

## Preparação

1. Em uma janela aprovada, identifique a revisão atualmente publicada, o checkout, o ambiente virtual, o Python e as configurações WSGI da aba **Web**. A revisão nova deve ser a mesma validada em homologação. [Configuração de Django no PythonAnywhere](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/)
2. Pela aba **Databases**, confirme o host e o nome completo do schema. Durante a janela, suspenda as escritas da aplicação e das rotinas agendadas. Copie as mídias públicas e privadas e preserve a configuração de storage. Faça e valide o backup restaurando-o em um schema separado. [Backup e restauração de MySQL](https://help.pythonanywhere.com/pages/MySQLBackupRestore/)

```bash
umask 077
mkdir -p "$HOME/saari-backup"
mysqldump --host=HOST_MYSQL --user=USUARIO --single-transaction --set-gtid-purged=OFF \
  --no-tablespaces 'USUARIO$SCHEMA' > "$HOME/saari-backup/pre-reestruturacao.sql"
```

3. Na cópia de homologação, valide as contagens e os vínculos de pedidos, recebimentos, títulos, pagamentos e anexos. Confirme o suporte de fuso do MySQL para `UTC` e `America/Sao_Paulo`. Inspecione o plano das migrações e ensaie em volume representativo. A alteração do índice do recebimento no Financeiro pode bloquear escritas conforme a versão e o volume. Reserve tempo para validar cada DDL antes de retomar o serviço.

## Publicação manual da revisão homologada

Disponibilize a revisão aprovada no checkout e ative o ambiente virtual já associado ao aplicativo. Use as configurações efetivas do host e confira novamente o destino do banco antes da aplicação manual.

```bash
git status --short --branch
git rev-parse HEAD
python -m pip check
python manage.py check
python manage.py showmigrations compras financeiro
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py showmigrations compras financeiro
python manage.py diagnosticar_reservas_compra
python manage.py diagnosticar_recebimentos_financeiros --somente-pendencias
python manage.py collectstatic --noinput
```

Confirme o mapeamento de `/static/` para o `STATIC_ROOT` e recarregue o aplicativo pela aba **Web**. Confira os arquivos estáticos, os logs, as permissões, um PDF com o logotipo do ambiente e os downloads autorizados. Verifique a fila, os compromissos e os valores de um recorte conhecido antes de liberar escritas. [Arquivos estáticos no PythonAnywhere](https://help.pythonanywhere.com/pages/DjangoStaticFiles/)

## Recuperação

- Se a falha ocorrer durante a atualização, mantenha as escritas suspensas. Confira `showmigrations` e o schema antes de repetir comandos. O MySQL pode ter confirmado parte do DDL mesmo quando a operação seguinte falhou.
- Se ainda não houver operações novas, recupere a revisão e a mídia compatíveis e valide a restauração em schema separado. A reversão das migrações 0017 e 0044 pode perder campos novos e só deve ser considerada quando a equipe conferir que eles estão sem uso. A regra de reversão impede restaurar a unicidade antiga quando há parcelas irmãs.
- Se a aplicação já recebeu operações na versão nova, preserve o estado posterior antes de decidir. Corrija na versão de esquema atual ou reconcilie as operações posteriores em uma cópia restaurada. Confira recebimentos, títulos, pagamentos, malotes e os arquivos vinculados antes de habilitar o tráfego.
- Repita a coleta de estáticos para a revisão recuperada, recarregue pela aba **Web** e execute as verificações de homologação aplicáveis.
