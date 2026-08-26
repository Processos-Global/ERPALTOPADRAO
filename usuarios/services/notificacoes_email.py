import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


logger = logging.getLogger(__name__)


def _nome_usuario(usuario):
    nome = (usuario.get_full_name() or "").strip()
    return nome or usuario.username


def _url_absoluta_notificacao(notificacao):
    destino = (notificacao.url or "").strip()

    if not destino:
        return ""

    if destino.startswith(("http://", "https://")):
        return destino

    base_url = str(getattr(settings, "ERP_BASE_URL", "") or "").strip()

    if not base_url:
        return ""

    return urljoin(
        base_url.rstrip("/") + "/",
        destino.lstrip("/"),
    )


def enviar_email_notificacao(notificacao):
    usuario = notificacao.usuario
    destinatario = (usuario.email or "").strip()

    if not destinatario:
        logger.info(
            "Notificação %s não enviada por e-mail: usuário %s sem e-mail cadastrado.",
            notificacao.pk,
            usuario.pk,
        )
        return False

    url_absoluta = _url_absoluta_notificacao(notificacao)

    contexto = {
        "notificacao": notificacao,
        "usuario": usuario,
        "nome_usuario": _nome_usuario(usuario),
        "url_absoluta": url_absoluta,
        "nome_sistema": "ERP Alto Padrão",
    }

    assunto = f"ERP Alto Padrão | {notificacao.titulo}"

    mensagem_texto = (
        f"Olá, {contexto['nome_usuario']}.\n\n"
        f"{notificacao.titulo}\n\n"
        f"{notificacao.mensagem}\n\n"
    )

    if url_absoluta:
        mensagem_texto += (
            "Acesse diretamente pelo link abaixo:\n"
            f"{url_absoluta}\n\n"
        )
    else:
        mensagem_texto += (
            "Acesse o ERP Alto Padrão para visualizar os detalhes.\n\n"
        )

    mensagem_texto += "ERP Alto Padrão"

    try:
        html = render_to_string(
            "usuarios/emails/notificacao.html",
            contexto,
        )

        email = EmailMultiAlternatives(
            subject=assunto,
            body=mensagem_texto,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario],
        )

        email.attach_alternative(html, "text/html")
        enviados = email.send(fail_silently=False)

        if enviados:
            logger.info(
                "Notificação %s enviada por e-mail para o usuário %s.",
                notificacao.pk,
                usuario.pk,
            )
            return True

        logger.warning(
            "Backend de e-mail não confirmou envio da notificação %s para o usuário %s.",
            notificacao.pk,
            usuario.pk,
        )
        return False

    except Exception:
        logger.exception(
            "Falha ao enviar notificação %s por e-mail para o usuário %s.",
            notificacao.pk,
            usuario.pk,
        )
        return False
