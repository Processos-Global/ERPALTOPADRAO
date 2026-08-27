from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from django.contrib.auth.models import User
from django.db import transaction

from usuarios.models import (
    ModuloSistema,
    NivelPermissao,
    PermissaoCadastros,
    PermissaoCompras,
    PermissaoModulo,
)


@dataclass(frozen=True)
class PermissaoEspecificaDef:
    campo: str
    rotulo: str
    descricao: str
    destaque: str = ""


@dataclass(frozen=True)
class ModuloDef:
    codigo: str
    titulo: str
    descricao: str
    icone: str
    ordem: int
    url_name: str = ""
    permissoes: tuple[PermissaoEspecificaDef, ...] = ()
    carregar_especificas: Callable[[User], dict] | None = None
    salvar_especificas: Callable[[User, dict, bool], None] | None = None
    resolver_nivel: Callable[[dict], str] | None = None


def _carregar_compras(usuario: User) -> dict:
    permissao, _ = PermissaoCompras.objects.get_or_create(usuario=usuario)
    return {
        "solicitar_compra": permissao.solicitar_compra,
        "executar_cotacao": permissao.executar_cotacao,
        "compatibilizar": permissao.compatibilizar,
        "negociar": permissao.negociar,
        "aprovar_compra": permissao.aprovar_compra,
        "gerenciar_pedidos": permissao.gerenciar_pedidos,
        "receber_pedidos": permissao.receber_pedidos,
        "cancelar_pedidos": permissao.cancelar_pedidos,
        "administrar": permissao.administrar,
    }



def _carregar_cadastros(usuario: User) -> dict:
    permissao, _ = PermissaoCadastros.objects.get_or_create(usuario=usuario)
    return {
        "visualizar": permissao.visualizar,
        "criar": permissao.criar,
        "editar": permissao.editar,
        "excluir": permissao.excluir,
        "administrar": permissao.administrar,
    }


def _resolver_nivel_cadastros(valores: dict) -> str:
    if valores.get("administrar"):
        return NivelPermissao.ADMINISTRADOR
    if any(valores.get(campo) for campo in ("criar", "editar", "excluir")):
        return NivelPermissao.EDICAO
    return NivelPermissao.LEITURA


def _salvar_cadastros(usuario: User, valores: dict, modulo_ativo: bool) -> None:
    permissao, _ = PermissaoCadastros.objects.get_or_create(usuario=usuario)
    permissao.visualizar = modulo_ativo and bool(valores.get("visualizar", True))
    permissao.criar = modulo_ativo and bool(valores.get("criar", False))
    permissao.editar = modulo_ativo and bool(valores.get("editar", False))
    permissao.excluir = modulo_ativo and bool(valores.get("excluir", False))
    permissao.administrar = modulo_ativo and bool(valores.get("administrar", False))
    permissao.ativo = modulo_ativo
    permissao.save()


def _resolver_nivel_compras(valores: dict) -> str:
    if valores.get("administrar"):
        return NivelPermissao.ADMINISTRADOR
    if valores.get("aprovar_compra"):
        return NivelPermissao.APROVACAO
    if any(
        valores.get(campo)
        for campo in (
            "solicitar_compra",
            "executar_cotacao",
            "compatibilizar",
            "negociar",
            "gerenciar_pedidos",
            "receber_pedidos",
            "cancelar_pedidos",
        )
    ):
        return NivelPermissao.EDICAO
    return NivelPermissao.LEITURA


def _salvar_compras(usuario: User, valores: dict, modulo_ativo: bool) -> None:
    permissao, _ = PermissaoCompras.objects.get_or_create(usuario=usuario)
    permissao.visualizar = modulo_ativo
    permissao.ativo = modulo_ativo
    for campo in (
        "solicitar_compra",
        "executar_cotacao",
        "compatibilizar",
        "negociar",
        "aprovar_compra",
        "gerenciar_pedidos",
        "receber_pedidos",
        "cancelar_pedidos",
        "administrar",
    ):
        setattr(permissao, campo, bool(valores.get(campo, False)))
    permissao.save()


# Registry central. Para incluir um módulo futuro na tela, adicione apenas uma
# definição aqui. Permissões específicas são opcionais e podem ser conectadas
# posteriormente sem reescrever views ou templates.
MODULOS_REGISTRY: tuple[ModuloDef, ...] = (
    ModuloDef(
        codigo=ModuloSistema.OBRAS,
        titulo="Obras",
        descricao="Cadastro e informações gerais das obras.",
        icone="building",
        ordem=10,
        url_name="",
    ),
    ModuloDef(
        codigo=ModuloSistema.CADASTROS,
        titulo="Cadastros",
        descricao="Central de materiais, fornecedores e mão de obra do ERP.",
        icone="file",
        ordem=15,
        url_name="cadastros:index",
        permissoes=(
            PermissaoEspecificaDef("visualizar", "Visualizar cadastros", "Pode consultar materiais, fornecedores e mão de obra."),
            PermissaoEspecificaDef("criar", "Criar cadastros", "Pode cadastrar novos materiais, fornecedores e mão de obra."),
            PermissaoEspecificaDef("editar", "Editar cadastros", "Pode alterar registros existentes da central de cadastros."),
            PermissaoEspecificaDef("excluir", "Excluir cadastros", "Pode excluir registros quando não houver vínculos protegidos.", "danger"),
            PermissaoEspecificaDef("administrar", "Administrar Cadastros", "Concede acesso total às ações do módulo.", "admin"),
        ),
        carregar_especificas=_carregar_cadastros,
        salvar_especificas=_salvar_cadastros,
        resolver_nivel=_resolver_nivel_cadastros,
    ),
    ModuloDef(
        codigo=ModuloSistema.PLANEJAMENTO,
        titulo="Planejamento",
        descricao="Cronogramas, planejamento e acompanhamento da obra.",
        icone="calendar",
        ordem=20,
        url_name="planejamento:painel_cronograma",
    ),
    ModuloDef(
        codigo=ModuloSistema.SUPRIMENTOS,
        titulo="Suprimentos",
        descricao="Cronograma e planejamento de suprimentos.",
        icone="package",
        ordem=30,
        url_name="planejamento:painel_cronograma_suprimentos",
    ),
    ModuloDef(
        codigo=ModuloSistema.COMPRAS,
        titulo="Compras",
        descricao="Processos de compra, cotação, aprovação, pedidos e recebimentos.",
        icone="cart",
        ordem=40,
        url_name="compras:dashboard",
        permissoes=(
            PermissaoEspecificaDef("solicitar_compra", "Solicitar compra", "Pode abrir processos e registrar necessidades."),
            PermissaoEspecificaDef("executar_cotacao", "Executar cotação", "Pode selecionar fornecedores, lançar propostas e concluir cotações."),
            PermissaoEspecificaDef("compatibilizar", "Compatibilizar", "Pode executar a análise técnica e concluir a compatibilização."),
            PermissaoEspecificaDef("negociar", "Negociar", "Pode registrar negociação e concluir a etapa comercial."),
            PermissaoEspecificaDef("aprovar_compra", "Aprovar compra", "Pode aprovar, reprovar ou solicitar ajustes."),
            PermissaoEspecificaDef("gerenciar_pedidos", "Gerenciar pedidos", "Pode anexar documentos e atualizar status e previsão."),
            PermissaoEspecificaDef("receber_pedidos", "Registrar recebimentos", "Pode registrar recebimentos, valores e nota fiscal."),
            PermissaoEspecificaDef("cancelar_pedidos", "Cancelar pedidos", "Pode cancelar pedidos quando a regra de negócio permitir.", "danger"),
            PermissaoEspecificaDef("administrar", "Administrar Compras", "Concede acesso total às ações de Compras.", "admin"),
        ),
        carregar_especificas=_carregar_compras,
        salvar_especificas=_salvar_compras,
        resolver_nivel=_resolver_nivel_compras,
    ),
    ModuloDef(ModuloSistema.CONTRATOS, "Contratos", "Gestão de contratos e documentos contratuais.", "file", 50, ""),
    ModuloDef(ModuloSistema.FINANCEIRO, "Financeiro", "Lançamentos, aprovações e acompanhamento financeiro.", "wallet", 60, ""),
    ModuloDef(ModuloSistema.ALMOXARIFADO, "Almoxarifado", "Entradas, saídas, estoque e transferências.", "warehouse", 70, ""),
    ModuloDef(ModuloSistema.PROJETOS, "Projetos", "Gestão e acompanhamento de projetos.", "ruler", 80, ""),
    ModuloDef(ModuloSistema.VISTORIAS, "Vistorias", "Inspeções, vistorias e registros de campo.", "check", 90, ""),
    ModuloDef(ModuloSistema.DIARIO_OBRA, "Diário de obra", "Registros diários e acompanhamento de campo.", "book", 100, ""),
    ModuloDef(ModuloSistema.POS_OBRA, "Pós-obra", "Atendimento, garantias e ordens de serviço.", "tools", 110, ""),
    ModuloDef(ModuloSistema.RELATORIOS, "Relatórios", "Relatórios e consultas consolidadas.", "chart", 120, ""),
    ModuloDef(ModuloSistema.INTEGRACOES, "Integrações", "Integrações e rotinas de comunicação entre sistemas.", "refresh", 130, ""),
    ModuloDef(ModuloSistema.USUARIOS, "Usuários e permissões", "Gerenciamento de usuários e acessos do ERP.", "users", 140, "usuarios:lista_usuarios"),
)


def _nivel_valido(valor: str) -> str:
    niveis = {item[0] for item in NivelPermissao.choices}
    return valor if valor in niveis else NivelPermissao.LEITURA


def obter_configuracao_modulos_usuario(usuario: User) -> list[dict]:
    permissoes_modulo = {
        permissao.modulo: permissao
        for permissao in PermissaoModulo.objects.filter(usuario=usuario)
    }

    resultado = []
    for definicao in sorted(MODULOS_REGISTRY, key=lambda item: item.ordem):
        geral = permissoes_modulo.get(definicao.codigo)
        especificas_valores = (
            definicao.carregar_especificas(usuario)
            if definicao.carregar_especificas
            else {}
        )

        especificas = []
        for permissao in definicao.permissoes:
            especificas.append(
                {
                    "campo": permissao.campo,
                    "rotulo": permissao.rotulo,
                    "descricao": permissao.descricao,
                    "destaque": permissao.destaque,
                    "marcada": bool(especificas_valores.get(permissao.campo, False)),
                    "input_name": f"perm__{definicao.codigo}__{permissao.campo}",
                }
            )

        resultado.append(
            {
                "codigo": definicao.codigo,
                "titulo": definicao.titulo,
                "descricao": definicao.descricao,
                "icone": definicao.icone,
                "ativo": bool(geral and geral.ativo),
                "nivel": geral.nivel if geral else NivelPermissao.LEITURA,
                "input_ativo": f"modulo__{definicao.codigo}__ativo",
                "input_nivel": f"modulo__{definicao.codigo}__nivel",
                "niveis": NivelPermissao.choices,
                "permissoes": especificas,
                "tem_permissoes_especificas": bool(especificas),
                "nivel_automatico": bool(definicao.resolver_nivel),
            }
        )

    return resultado


@transaction.atomic
def salvar_configuracao_modulos_usuario(usuario: User, post_data, usuario_executor: User | None = None) -> None:
    for definicao in MODULOS_REGISTRY:
        ativo = post_data.get(f"modulo__{definicao.codigo}__ativo") == "on"
        proteger_proprio_admin = (
            definicao.codigo == ModuloSistema.USUARIOS
            and usuario_executor is not None
            and usuario.pk == usuario_executor.pk
            and not usuario_executor.is_superuser
        )
        if proteger_proprio_admin:
            ativo = True
        valores = {
            permissao.campo: post_data.get(
                f"perm__{definicao.codigo}__{permissao.campo}"
            ) == "on"
            for permissao in definicao.permissoes
        }

        if definicao.resolver_nivel:
            nivel = definicao.resolver_nivel(valores)
        else:
            nivel = _nivel_valido(post_data.get(f"modulo__{definicao.codigo}__nivel", ""))
        if proteger_proprio_admin:
            nivel = NivelPermissao.ADMINISTRADOR

        PermissaoModulo.objects.update_or_create(
            usuario=usuario,
            modulo=definicao.codigo,
            defaults={"ativo": ativo, "nivel": nivel},
        )

        if definicao.salvar_especificas:
            definicao.salvar_especificas(usuario, valores, ativo)
