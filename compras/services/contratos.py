from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from compras.models import ContratoCompra, HistoricoContratoCompra
from compras.services.contratos_drive import (
    exportar_docx_bytes,
    finalizar_google_doc,
    gerar_previa_google_doc,
    upload_contrato_assinado,
)
from compras.services.numeracao import gerar_numero


def registrar_historico(contrato, evento, usuario=None, descricao=""):
    return HistoricoContratoCompra.objects.create(
        contrato=contrato,
        evento=evento,
        usuario=usuario,
        descricao=descricao or "",
    )


def _email_usuario(usuario):
    return (getattr(usuario, "email", "") or "").strip()


def _enviar_email(destinatario, assunto, mensagem, anexo_nome=None, anexo_bytes=None):
    if not destinatario:
        return False
    email = EmailMessage(
        subject=assunto,
        body=mensagem,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[destinatario],
    )
    if anexo_nome and anexo_bytes:
        email.attach(
            anexo_nome,
            anexo_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    email.send(fail_silently=False)
    return True


@transaction.atomic
def criar_contrato(*, form, usuario):
    contrato = form.save(commit=False)
    contrato.numero = gerar_numero("CONTRATO")
    contrato.criado_por = usuario
    contrato.status = ContratoCompra.Status.RASCUNHO
    contrato.save()
    registrar_historico(contrato, "CRIADO", usuario, "Contrato criado como rascunho.")
    return contrato


def atualizar_contrato(*, form, usuario):
    contrato = form.instance
    if not contrato.pode_editar:
        raise ValueError("Este contrato não pode mais ser editado.")
    contrato = form.save()
    registrar_historico(contrato, "EDITADO", usuario, "Dados do contrato atualizados.")
    return contrato


def gerar_previa(*, contrato, usuario):
    if not contrato.pode_editar:
        raise ValueError("A prévia só pode ser regenerada em rascunhos ou contratos devolvidos.")
    url = gerar_previa_google_doc(contrato)
    registrar_historico(contrato, "PREVIA_GERADA", usuario, "Prévia gerada no Google Drive.")
    return url


@transaction.atomic
def enviar_para_aprovacao(*, contrato, usuario):
    if not contrato.pode_editar:
        raise ValueError("Contrato não está disponível para envio à aprovação.")
    gerar_previa_google_doc(contrato)
    contrato.status = ContratoCompra.Status.AGUARDANDO_APROVACAO
    contrato.enviado_aprovacao_em = timezone.now()
    contrato.motivo_decisao = ""
    contrato.save(update_fields=["status", "enviado_aprovacao_em", "motivo_decisao", "atualizado_em"])
    registrar_historico(contrato, "ENVIADO_APROVACAO", usuario, "Contrato enviado ao gestor.")
    return contrato


@transaction.atomic
def decidir_contrato(*, contrato, usuario, decisao, observacao=""):
    if contrato.status != ContratoCompra.Status.AGUARDANDO_APROVACAO:
        raise ValueError("Este contrato não está aguardando aprovação.")

    agora = timezone.now()
    contrato.aprovado_por = usuario
    contrato.decidido_em = agora
    contrato.motivo_decisao = observacao or ""

    if decisao == "DEVOLVER":
        contrato.status = ContratoCompra.Status.DEVOLVIDO
        contrato.save(update_fields=["status", "aprovado_por", "decidido_em", "motivo_decisao", "atualizado_em"])
        registrar_historico(contrato, "DEVOLVIDO", usuario, observacao)
        _enviar_email(
            _email_usuario(contrato.criado_por),
            f"{contrato.numero} devolvido para correção",
            f"O contrato {contrato.numero} foi devolvido para correção.\n\nMotivo:\n{observacao}",
        )
        return contrato

    if decisao == "REPROVAR":
        contrato.status = ContratoCompra.Status.REPROVADO
        contrato.save(update_fields=["status", "aprovado_por", "decidido_em", "motivo_decisao", "atualizado_em"])
        registrar_historico(contrato, "REPROVADO", usuario, observacao)
        _enviar_email(
            _email_usuario(contrato.criado_por),
            f"{contrato.numero} reprovado",
            f"O contrato {contrato.numero} foi reprovado.\n\nMotivo:\n{observacao}",
        )
        return contrato

    if decisao != "APROVAR":
        raise ValueError("Decisão inválida.")

    finalizar_google_doc(contrato)
    docx = exportar_docx_bytes(contrato)
    nome = f"{contrato.numero} - {contrato.contratado_razao_social}.docx"
    contrato.arquivo_docx.save(nome, ContentFile(docx), save=False)
    contrato.status = ContratoCompra.Status.AGUARDANDO_ASSINATURA
    contrato.save(update_fields=[
        "status", "aprovado_por", "decidido_em", "motivo_decisao",
        "arquivo_docx", "google_doc_url", "atualizado_em",
    ])
    registrar_historico(contrato, "APROVADO", usuario, "Contrato aprovado e DOCX final gerado.")

    mensagem = (
        f"O contrato {contrato.numero} foi aprovado.\n\n"
        "O arquivo DOCX segue anexo. Complete manualmente o Anexo 1 - Cronograma Físico-Financeiro, "
        "providencie as assinaturas e depois anexe o contrato assinado no SAARI ERP.\n\n"
        f"Documento no Google Drive: {contrato.google_doc_url}"
    )
    _enviar_email(
        _email_usuario(contrato.criado_por),
        f"{contrato.numero} aprovado - contrato em DOCX",
        mensagem,
        anexo_nome=nome,
        anexo_bytes=docx,
    )
    return contrato


@transaction.atomic
def confirmar_assinatura(*, contrato, arquivo, usuario):
    if contrato.status != ContratoCompra.Status.AGUARDANDO_ASSINATURA:
        raise ValueError("Este contrato não está aguardando assinatura.")
    contrato.arquivo_assinado = arquivo
    contrato.assinado_em = timezone.now()
    contrato.status = ContratoCompra.Status.ASSINADO
    contrato.save(update_fields=["arquivo_assinado", "assinado_em", "status", "atualizado_em"])
    upload_contrato_assinado(contrato)
    registrar_historico(contrato, "ASSINADO", usuario, "Assinatura confirmada e arquivo assinado anexado.")
    return contrato
