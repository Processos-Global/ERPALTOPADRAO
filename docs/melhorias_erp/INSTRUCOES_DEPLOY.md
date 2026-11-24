# Publicação no PythonAnywhere

Execute numa janela de manutenção autorizada e após revisar o diff, os testes e o ambiente de homologação. Use o caminho do checkout, a virtualenv e o procedimento de backup já configurados para a aplicação. Guarde a revisão atual e valide o backup do MySQL pelo painel ou pelo procedimento aprovado, sem incluir credenciais na linha de comando.

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

Confirme que `origin/main` contém a revisão aprovada antes do fast-forward. A entrega não exige alteração de dependências ou esquema. Faça o reload da aplicação pela aba Web do PythonAnywhere e confira os logs de erro.

Valide autenticação, permissões, filtro e download, paginação do Diário e de Projetos, listagem de Compras, seleção de material na Ficha Técnica e abertura de abas e itens em Planejamento. Valide o fluxo transacional de reservas com dados exclusivos de homologação em MySQL antes da publicação.

Para rollback, selecione a revisão estável registrada, usando o procedimento de releases do ambiente. Reexecute `python manage.py check` e `python manage.py collectstatic --noinput` a partir dessa revisão e recarregue o app. Em checkout dedicado e limpo, a revisão anterior também pode ser servida temporariamente com `git switch --detach REVISAO_ANTERIOR`. Confirme logs, login e páginas críticas após o reload.
`collectstatic` e reload seguem a [documentação de arquivos estáticos do PythonAnywhere](https://help.pythonanywhere.com/pages/DjangoStaticFiles/).
