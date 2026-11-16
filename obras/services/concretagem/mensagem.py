"""Mensagem de solicitação para a concreteira (texto para WhatsApp e e-mail HTML)."""
import logging
from urllib.parse import quote, urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.urls import reverse

from cadastros.models import DadosEmpresa
from obras.models import ContatoEmailConcreteira

logger = logging.getLogger(__name__)

DIAS_SEMANA = ("SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO")


def _num(valor):
    if valor is None:
        return ""
    texto = f"{valor:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def url_absoluta(caminho, request=None):
    if request is not None:
        return request.build_absolute_uri(caminho)
    base = str(getattr(settings, "SITE_URL", "") or "").strip()
    return urljoin(base.rstrip("/") + "/", caminho.lstrip("/")) if base else caminho


def link_publico(conc, request=None):
    return url_absoluta(reverse("obras:concretagem_publica", args=[conc.token_confirmacao]), request)


def _empresa():
    empresa = DadosEmpresa.atual()
    if not empresa:
        return "", ""
    return (empresa.razao_social or empresa.nome_fantasia or "").upper(), empresa.cnpj or ""


def gerar_texto(conc, request=None, incluir_link=True):
    obra = conc.obra
    data = conc.data_programada
    data_fmt = f"{data:%d/%m/%Y} - {DIAS_SEMANA[data.weekday()]}" if data else "A DEFINIR"
    hora_fmt = f"{conc.horario_programado:%H:%M} HORAS" if conc.horario_programado else "A DEFINIR"

    servicos = []
    for item in conc.itens_planejados.select_related("local"):
        linha = item.titulo.upper()
        if item.volume_previsto:
            linha += f" ({_num(item.volume_previsto)} M³)"
        servicos.append(linha)

    linhas = [f"CONCRETAGEM {obra.nome.upper()}"]
    if conc.razao_social_empreendimento:
        linhas.append(f"EMPRESA: {conc.razao_social_empreendimento.upper()}")
    linhas += ["", "SERVIÇO:", *(servicos or ["—"]), ""]
    linhas.append(f"FCK: {_num(conc.fck_projeto)} MPA" if conc.fck_projeto else "FCK: A DEFINIR")
    if conc.slump:
        linhas.append(f"SLUMP FLOW: {conc.slump_texto.upper()}")
    if conc.agregado:
        linhas.append(f"AGREGADO: {conc.agregado.upper()}")
    linhas.append(f"VOLUME PREVISTO: {_num(conc.volume_solicitado)} M³" if conc.volume_solicitado else "VOLUME PREVISTO: A DEFINIR")
    linhas += ["", f"DATA: {data_fmt}", f"HORÁRIO: {hora_fmt}"]
    if conc.com_bomba:
        linhas.append("COM BOMBA ESTACIONÁRIA" + (f" — BOMBISTA: {conc.nome_bombista.upper()}" if conc.nome_bombista else ""))
    if conc.observacoes:
        linhas += ["", conc.observacoes.upper()]

    nome_empresa, cnpj = _empresa()
    if nome_empresa:
        linhas += ["", nome_empresa]
        if cnpj:
            linhas.append(f"CNPJ: {cnpj}")

    endereco = conc.endereco_entrega or ", ".join(filter(None, [obra.endereco, obra.cidade]))
    if endereco:
        linhas += ["", "ENDEREÇO DE ENTREGA:", endereco]
    if conc.link_maps_entrega:
        linhas.append(conc.link_maps_entrega)
    if incluir_link:
        linhas += ["", "CONFIRMAR, RECUSAR OU PEDIR OUTRA DATA:", link_publico(conc, request)]
    return "\n".join(linhas)


def link_whatsapp(texto):
    return "https://wa.me/?text=" + quote(texto)


def destinatarios_sugeridos(conc):
    """E-mail do cadastro do fornecedor + contatos extras ativos da concreteira."""
    sugeridos = []
    if conc.concreteira_id and conc.concreteira.email:
        sugeridos.append({"email": conc.concreteira.email, "nome": "Cadastro do fornecedor", "contato": None})
    if conc.concreteira_id:
        for contato in ContatoEmailConcreteira.objects.filter(fornecedor_id=conc.concreteira_id, ativo=True):
            if all(s["email"].lower() != contato.email.lower() for s in sugeridos):
                sugeridos.append({"email": contato.email, "nome": contato.nome, "contato": contato})
    return sugeridos


def validar_emails(emails):
    validos = []
    for email in emails:
        email = (email or "").strip()
        if not email:
            continue
        try:
            validate_email(email)
        except ValidationError:
            raise ValueError(f"E-mail inválido: {email}")
        if email.lower() not in {e.lower() for e in validos}:
            validos.append(email)
    return validos


def enviar_email_aceite(conc, request=None):
    """Avisa o engenheiro responsável de que a concretagem foi aceita.

    Retorna True se enviou; sem e-mail cadastrado ou falha de SMTP, registra
    em log e retorna False (o aceite já está gravado e não é desfeito).
    """
    engenheiro = conc.engenheiro
    destino = (getattr(engenheiro, "email", "") or "").strip()
    if not destino:
        logger.warning("Concretagem %s aceita, mas o engenheiro não tem e-mail cadastrado.", conc.codigo)
        return False
    manual = conc.aceite_manual_por_id is not None
    contexto = {
        "conc": conc,
        "engenheiro": engenheiro,
        "itens": conc.itens_planejados.select_related("local"),
        "manual": manual,
        "link": url_absoluta(reverse("obras:concretagem_detalhe", args=[conc.pk]), request),
    }
    assunto = f"Concretagem aceita: {conc.codigo} — {conc.obra.nome}"
    if conc.data_programada:
        assunto += f" — {conc.data_programada:%d/%m/%Y}"
    quem = "pela equipe da obra (aceite manual)" if manual else f"pela concreteira {conc.concreteira_nome}"
    texto = (
        f"A concretagem {conc.codigo} da obra {conc.obra.nome} foi aceita {quem}.\n"
        f"Data: {conc.data_programada:%d/%m/%Y}" + (f" às {conc.horario_programado:%H:%M}" if conc.horario_programado else "")
        + f"\n\nAbrir no ERP: {contexto['link']}"
    ) if conc.data_programada else f"A concretagem {conc.codigo} foi aceita {quem}.\n\n{contexto['link']}"
    try:
        email = EmailMultiAlternatives(
            subject=assunto, body=texto,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None), to=[destino],
        )
        email.attach_alternative(render_to_string("obras/concretagem/email/aceite.html", contexto), "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Falha ao enviar e-mail de aceite da concretagem %s", conc.codigo)
        return False


def enviar_email(conc, destinatarios, request=None):
    """Envia a solicitação. Retorna True/False; falhas de SMTP são registradas em log."""
    contexto = {
        "conc": conc,
        "itens": conc.itens_planejados.select_related("local"),
        "link": link_publico(conc, request),
        "empresa": DadosEmpresa.atual(),
    }
    assunto = f"Solicitação de concretagem {conc.codigo} — {conc.obra.nome}"
    if conc.data_programada:
        assunto += f" — {conc.data_programada:%d/%m/%Y}"
    texto = gerar_texto(conc, request)
    html = render_to_string("obras/concretagem/email/solicitacao.html", contexto)
    try:
        email = EmailMultiAlternatives(
            subject=assunto, body=texto,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None), to=destinatarios,
        )
        email.attach_alternative(html, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Falha ao enviar e-mail da concretagem %s", conc.codigo)
        return False
