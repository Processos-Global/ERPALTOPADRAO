# Publicação no PythonAnywhere

Para publicar a revisão global, incluindo o Financeiro e as migrations, use as [instruções atuais](../reestruturacao_financeiro/INSTRUCOES_DEPLOY.md). O roteiro abaixo registra a primeira frente.

```bash
cd /caminho/do/checkout
source /caminho/da/virtualenv/bin/activate
git status --short
git rev-parse HEAD
git fetch origin
git log --oneline HEAD..origin/main
git merge --ff-only origin/main
python manage.py check
python manage.py collectstatic --noinput
```

Confirme que `origin/main` contém a revisão aprovada. Para a revisão atual, siga também as etapas de backup, diagnósticos de unicidade, fuso horário, migrations e reload do roteiro global.

Valide autenticação, permissões, filtro e download, paginação do Diário e de Projetos, listagem de Compras, seleção de material na Ficha Técnica e abertura de abas e itens em Planejamento. Valide o fluxo transacional de reservas com dados exclusivos de homologação em MySQL antes da publicação.

Para rollback, selecione a revisão estável registrada, usando o procedimento de releases do ambiente. Reexecute `python manage.py check` e `python manage.py collectstatic --noinput` a partir dessa revisão e recarregue o app. Em checkout dedicado e limpo, a revisão anterior também pode ser servida temporariamente com `git switch --detach REVISAO_ANTERIOR`. Confirme logs, login e páginas críticas após o reload.
`collectstatic` e reload seguem a [documentação de arquivos estáticos do PythonAnywhere](https://help.pythonanywhere.com/pages/DjangoStaticFiles/).
