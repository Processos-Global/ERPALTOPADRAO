from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from usuarios.models import (
    PerfilUsuario,
    PermissaoCompras,
    PermissaoModulo,
)


class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    fk_name = "usuario"
    extra = 0
    max_num = 1
    can_delete = False
    classes = ["collapse"]
    fields = [
        "cargo",
        "telefone",
        "foto",
        "ativo",
    ]
    verbose_name = "Perfil do ERP"
    verbose_name_plural = "Perfil do ERP"


class PermissaoComprasInline(admin.StackedInline):
    model = PermissaoCompras
    fk_name = "usuario"
    extra = 1
    max_num = 1
    can_delete = False

    fieldsets = (
        (
            "Acesso ao módulo",
            {
                "fields": (
                    "ativo",
                    "visualizar",
                ),
                "description": (
                    "Estas opções controlam as permissões específicas de Compras. "
                    "O usuário também precisa possuir uma Permissão de módulo ativa "
                    "para COMPRAS, exibida mais abaixo nesta mesma tela."
                ),
            },
        ),
        (
            "Solicitação e processo de compra",
            {
                "fields": (
                    "solicitar_compra",
                ),
                "description": (
                    "Permite iniciar processos de compra e informar as necessidades "
                    "de materiais/serviços."
                ),
            },
        ),
        (
            "Fluxo comercial",
            {
                "fields": (
                    "executar_cotacao",
                    "negociar",
                ),
                "description": (
                    "Cotação controla fornecedores e propostas. Negociação controla "
                    "os valores e condições comerciais após a compatibilização."
                ),
            },
        ),
        (
            "Análise técnica",
            {
                "fields": (
                    "compatibilizar",
                ),
                "description": (
                    "Permite executar a compatibilização técnica dos itens/propostas."
                ),
            },
        ),
        (
            "Aprovação do gestor",
            {
                "fields": (
                    "aprovar_compra",
                ),
                "description": (
                    "Permite aprovar, reprovar ou solicitar ajustes na etapa de "
                    "aprovação da compra."
                ),
            },
        ),
        (
            "Pedidos e recebimentos",
            {
                "fields": (
                    "gerenciar_pedidos",
                    "receber_pedidos",
                    "cancelar_pedidos",
                ),
                "description": (
                    "Gerenciar pedidos permite atualizar pedido, status, previsão e "
                    "documentos. Registrar recebimentos permite lançar recebimento e NF."
                ),
            },
        ),
        (
            "Administração de Compras",
            {
                "fields": (
                    "administrar",
                ),
                "description": (
                    "Administrar Compras concede acesso a todas as ações do módulo, "
                    "independentemente dos demais checkboxes."
                ),
            },
        ),
    )

    verbose_name = "Permissões específicas de Compras"
    verbose_name_plural = "Permissões específicas de Compras"


class PermissaoModuloInline(admin.TabularInline):
    model = PermissaoModulo
    fk_name = "usuario"
    extra = 0
    fields = [
        "modulo",
        "nivel",
        "ativo",
    ]
    verbose_name = "Permissão de módulo"
    verbose_name_plural = "Permissões de acesso aos módulos"


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = [
        "usuario",
        "cargo",
        "ativo",
        "criado_em",
    ]

    list_filter = [
        "cargo",
        "ativo",
    ]

    search_fields = [
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
    ]

    autocomplete_fields = [
        "usuario",
    ]

    readonly_fields = [
        "criado_em",
        "atualizado_em",
    ]

    fieldsets = (
        (
            "Usuário",
            {
                "fields": (
                    "usuario",
                    "cargo",
                    "telefone",
                    "foto",
                    "ativo",
                ),
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "criado_em",
                    "atualizado_em",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(PermissaoModulo)
class PermissaoModuloAdmin(admin.ModelAdmin):
    list_display = [
        "usuario",
        "modulo",
        "nivel",
        "ativo",
    ]

    list_editable = [
        "nivel",
        "ativo",
    ]

    list_filter = [
        "modulo",
        "nivel",
        "ativo",
    ]

    search_fields = [
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
    ]

    autocomplete_fields = [
        "usuario",
    ]

    readonly_fields = [
        "criado_em",
        "atualizado_em",
    ]

    ordering = [
        "usuario__username",
        "modulo",
    ]


@admin.register(PermissaoCompras)
class PermissaoComprasAdmin(admin.ModelAdmin):
    list_display = [
        "usuario",
        "visualizar",
        "solicitar_compra",
        "executar_cotacao",
        "compatibilizar",
        "negociar",
        "aprovar_compra",
        "gerenciar_pedidos",
        "receber_pedidos",
        "cancelar_pedidos",
        "administrar",
        "ativo",
    ]

    # Facilita os testes: as permissões podem ser marcadas diretamente
    # na listagem do Django Admin, sem precisar abrir cada registro.
    list_editable = [
        "visualizar",
        "solicitar_compra",
        "executar_cotacao",
        "compatibilizar",
        "negociar",
        "aprovar_compra",
        "gerenciar_pedidos",
        "receber_pedidos",
        "cancelar_pedidos",
        "administrar",
        "ativo",
    ]

    list_filter = [
        "ativo",
        "visualizar",
        "solicitar_compra",
        "executar_cotacao",
        "compatibilizar",
        "negociar",
        "aprovar_compra",
        "gerenciar_pedidos",
        "receber_pedidos",
        "cancelar_pedidos",
        "administrar",
    ]

    search_fields = [
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
    ]

    autocomplete_fields = [
        "usuario",
    ]

    readonly_fields = [
        "criado_em",
        "atualizado_em",
    ]

    ordering = [
        "usuario__first_name",
        "usuario__username",
    ]

    list_per_page = 50

    fieldsets = (
        (
            "Usuário e acesso",
            {
                "fields": (
                    "usuario",
                    "ativo",
                    "visualizar",
                ),
                "description": (
                    "O usuário também precisa possuir acesso ativo ao módulo COMPRAS "
                    "em Permissões de módulo."
                ),
            },
        ),
        (
            "Solicitação",
            {
                "fields": (
                    "solicitar_compra",
                ),
            },
        ),
        (
            "Cotação e negociação",
            {
                "fields": (
                    "executar_cotacao",
                    "negociar",
                ),
            },
        ),
        (
            "Compatibilização técnica",
            {
                "fields": (
                    "compatibilizar",
                ),
            },
        ),
        (
            "Aprovação",
            {
                "fields": (
                    "aprovar_compra",
                ),
            },
        ),
        (
            "Pedidos e recebimentos",
            {
                "fields": (
                    "gerenciar_pedidos",
                    "receber_pedidos",
                    "cancelar_pedidos",
                ),
            },
        ),
        (
            "Administrador",
            {
                "fields": (
                    "administrar",
                ),
                "description": (
                    "Quando marcado, o usuário pode executar todas as ações de Compras."
                ),
            },
        ),
        (
            "Auditoria",
            {
                "fields": (
                    "criado_em",
                    "atualizado_em",
                ),
                "classes": ("collapse",),
            },
        ),
    )


class ERPUserAdmin(DjangoUserAdmin):
    """
    Mantém toda a tela padrão de usuários do Django e acrescenta, no final,
    o perfil ERP, as permissões específicas de Compras e as permissões gerais
    de módulos.
    """

    inlines = [
        PerfilUsuarioInline,
        PermissaoComprasInline,
        PermissaoModuloInline,
    ]

    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "cargo_erp",
        "compras_ativo",
        "is_staff",
        "is_active",
    ]

    list_filter = [
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
        "perfil_erp__cargo",
        "permissao_compras_erp__ativo",
    ]

    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
    ]

    @admin.display(
        description="Cargo/setor",
        ordering="perfil_erp__cargo",
    )
    def cargo_erp(self, obj):
        try:
            return obj.perfil_erp.get_cargo_display()
        except PerfilUsuario.DoesNotExist:
            return "—"

    @admin.display(
        boolean=True,
        description="Compras",
        ordering="permissao_compras_erp__ativo",
    )
    def compras_ativo(self, obj):
        try:
            return obj.permissao_compras_erp.ativo
        except PermissaoCompras.DoesNotExist:
            return False


# O User já é registrado pelo django.contrib.auth. Substituímos somente
# a classe de administração, preservando toda a funcionalidade padrão.
admin.site.unregister(User)
admin.site.register(User, ERPUserAdmin)
