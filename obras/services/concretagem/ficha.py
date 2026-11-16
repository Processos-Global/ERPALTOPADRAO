"""Ficha de Moldagem de CP's (SENAI FO-POP-LABCON001-IST-01 Rev. 08) por overlay no PDF oficial.

Os valores são desenhados por cima do modelo original, nas coordenadas de
cada campo (portadas do sistema anterior), então o documento final é o PDF
aprovado, com os dados preenchidos. Até 5 séries (caminhões) por ficha; com
mais caminhões, gera uma ficha a mais a cada 5.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import black
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from cadastros.models import DadosEmpresa
from obras.models import AnexoConcretagem, FichaMoldagem

from . import drive

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "recursos" / "concretagem" / "ficha_moldagem_senai.pdf"
SERIES_POR_FICHA = 5
_PAGE_H = 596.04
_PAGE_W = 842.04

_LOCAL_CHECKBOX_X = {
    "ESTACA": (496.8, 508.8), "TUBULAO": (537.5, 549.6), "BLOCO": (586.9, 598.9),
    "VIGA_BALDRAME": (626.9, 638.9), "RADIER": (699.5, 711.5), "PILAR": (739.3, 751.3),
    "VIGA": (773.5, 785.5),
}
_LOCAL_CHECKBOX_X_LINHA2 = {
    "PAREDE": (496.8, 508.8), "CONTENCAO": (538.4, 550.4), "CORTINA": (596.0, 606.2),
    "ESCADA": (641.4, 653.3), "PISO": (683.1, 695.1), "LAJE": (714.0, 725.9),
    "SAPATA": (745.9, 757.8),
}
_RAMPA_CHECKBOX_X = (496.8, 508.8)
_SERIE0_LOCAL_Y = [287.0, 296.8, 306.6]
_SERIE_ROW_STEP = 33.5
_SERIE0_DATA_Y = 291.0
_COL_X = {
    "numero_serie": 30, "quantidade_cp": 51, "abatimento_medido": 90, "slump_flow": 143,
    "numero_nota_fiscal": 197, "hora_moldagem": 258, "inicio_mistura": 297, "chegada_obra": 337,
    "inicio_descarga": 390, "termino_descarga": 427, "concreto_aplicado_m3": 466,
}
JUNTA_X, PAV_X, TORRE_X = 597.0, 662.7, 722.6
_SIZE_CAMPO, _SIZE_CAMPO_PEQUENO, _SIZE_CHECKBOX = 9, 8, 8
_SERIE2_BOX = {
    1: (36.0, 108.0, 806.0, 168.0), 2: (36.0, 190.0, 806.0, 250.0), 3: (36.0, 273.5, 806.0, 333.5),
    4: (36.0, 357.0, 806.0, 417.0), 5: (36.0, 441.0, 806.0, 501.0),
}


def _fmt(valor):
    """Texto do campo; números decimais com vírgula (ex.: 7,50)."""
    if valor is None or valor == "":
        return ""
    texto = str(valor)
    return texto.replace(".", ",") if hasattr(valor, "quantize") else texto


def _fmt_hora(valor):
    return valor.strftime("%H:%M") if valor else ""


def _y(y_topo):
    return _PAGE_H - y_topo


def _draw(c, x, y_topo, texto, size=_SIZE_CAMPO, font="Helvetica"):
    if not texto:
        return
    c.setFont(font, size)
    c.setFillColor(black)
    c.drawString(x, _y(y_topo), texto)


def _draw_hora_hm(c, x_hora, x_minuto, y_topo, valor, size=_SIZE_CAMPO_PEQUENO):
    if valor:
        _draw(c, x_hora, y_topo, valor.strftime("%H"), size=size)
        _draw(c, x_minuto, y_topo, valor.strftime("%M"), size=size)


def _draw_x(c, x0, x1, y_topo, size=_SIZE_CHECKBOX):
    c.setFont("Helvetica-Bold", size)
    c.setFillColor(black)
    largura = c.stringWidth("X", "Helvetica-Bold", size)
    c.drawString((x0 + x1) / 2 - largura / 2, _y(y_topo), "X")


def _empresa(conc, ficha):
    if ficha.empresa:
        return ficha.empresa
    empresa = DadosEmpresa.atual()
    return (empresa.razao_social or empresa.nome_fantasia) if empresa else ""


def _overlay_pagina1(c, conc, ficha, caminhoes):
    _draw(c, 75, 92.5, _empresa(conc, ficha))
    _draw(c, 365, 92.5, ficha.referencia or conc.codigo, size=7)
    _draw(c, 53, 115.4, conc.obra.nome)
    _draw(c, 318, 115.4, ficha.central_concreto or conc.concreteira_nome)
    _draw(c, 55, 137.7, _fmt(conc.fck_projeto))
    _draw(c, 176, 137.7, ficha.abatimento)
    _draw(c, 224, 137.7, ficha.abatimento_tolerancia)
    _draw(c, 329, 137.7, ficha.slump_flow)
    _draw(c, 381, 137.7, ficha.slump_flow_tolerancia)
    if ficha.tempo == "SOL":
        _draw_x(c, 57.7, 64.5, 159.5)
    elif ficha.tempo == "CHUVA":
        _draw_x(c, 82.3, 89.2, 159.5)
    data = ficha.data or conc.data_programada
    _draw(c, 223, 159.5, data.strftime("%d/%m/%Y") if data else "")
    if ficha.local_moldagem == "LABORATORIO":
        _draw_x(c, 71.5, 78.3, 180.4)
    elif ficha.local_moldagem == "OBRA":
        _draw_x(c, 72.0, 78.8, 191.4)
    _draw(c, 512, 90.4, (ficha.observacoes or "")[:60], size=_SIZE_CAMPO_PEQUENO)
    _draw(c, 605, 134.3, ficha.idade_ruptura, size=_SIZE_CAMPO_PEQUENO)
    _draw_hora_hm(c, 515, 532, 157.4, ficha.hora_entrada)
    _draw_hora_hm(c, 620, 640, 157.4, ficha.hora_saida)
    _draw(c, 480, 180.5, ficha.moldador, size=_SIZE_CAMPO_PEQUENO)
    _draw(c, 597, 203.4, ficha.responsavel_conferencia, size=_SIZE_CAMPO_PEQUENO)
    if ficha.autorizacao == "INICIO_DESCARGA":
        _draw_x(c, 733.9, 744.8, 129.3)
    elif ficha.autorizacao == "TERCO_MEDIO":
        _draw_x(c, 787.1, 797.9, 129.3)

    p = _SIZE_CAMPO_PEQUENO
    for idx, cam in enumerate(caminhoes[:SERIES_POR_FICHA]):
        serie = cam.serie_moldagem
        y = _SERIE0_DATA_Y + idx * _SERIE_ROW_STEP
        _draw(c, _COL_X["numero_serie"], y, str(cam.ordem), size=p)
        _draw(c, _COL_X["quantidade_cp"], y, str(cam.cps_moldados or ""), size=p)
        _draw(c, _COL_X["abatimento_medido"], y, serie.abatimento_medido, size=p)
        tolerancia = serie.slump_flow_tolerancia_valor
        slump = (serie.slump_flow_valor or "") + (f" ±{tolerancia}" if tolerancia else "")
        _draw(c, _COL_X["slump_flow"], y, slump, size=7)
        _draw(c, _COL_X["numero_nota_fiscal"], y, cam.numero_nota_fiscal, size=p)
        _draw(c, _COL_X["hora_moldagem"], y, _fmt_hora(serie.hora_moldagem), size=p)
        _draw(c, _COL_X["inicio_mistura"], y, _fmt_hora(serie.inicio_mistura), size=p)
        _draw(c, _COL_X["chegada_obra"], y, _fmt_hora(cam.horario_chegada), size=p)
        _draw(c, _COL_X["inicio_descarga"], y, _fmt_hora(cam.inicio_descarga), size=p)
        _draw(c, _COL_X["termino_descarga"], y, _fmt_hora(cam.termino_descarga), size=p)
        _draw(c, _COL_X["concreto_aplicado_m3"], y, _fmt(serie.concreto_aplicado), size=p)

        local = (serie.local_aplicacao or "").upper()
        y1, y2, y3 = (v + idx * _SERIE_ROW_STEP for v in _SERIE0_LOCAL_Y)
        if local in _LOCAL_CHECKBOX_X:
            _draw_x(c, *_LOCAL_CHECKBOX_X[local], y1 + 3)
        elif local in _LOCAL_CHECKBOX_X_LINHA2:
            _draw_x(c, *_LOCAL_CHECKBOX_X_LINHA2[local], y2 + 3)
        elif local == "RAMPA":
            _draw_x(c, *_RAMPA_CHECKBOX_X, y3 + 3)
        if serie.junta:
            _draw(c, JUNTA_X + 30, y3 + 2, serie.junta[:10], size=6)
        if serie.pavimento:
            _draw(c, PAV_X + 30, y3 + 2, serie.pavimento[:10], size=6)
        if serie.torre:
            _draw(c, TORRE_X + 38, y3 + 2, serie.torre[:10], size=6)


def _imagem_etiqueta(anexo):
    """Abre a foto (local ou do Drive), aplica EXIF e deixa deitada. None se falhar."""
    try:
        im = Image.open(io.BytesIO(drive.ler_bytes(anexo)))
        im = ImageOps.exif_transpose(im)
        if im.height > im.width:
            im = im.transpose(Image.Transpose.ROTATE_90)
        im.load()
        return im
    except Exception:
        logger.exception("Não foi possível ler a etiqueta %s para a ficha", anexo.pk)
        return None


def _overlay_pagina2(c, conc, ficha, caminhoes):
    _draw(c, 100, 61.5, _empresa(conc, ficha))
    data = ficha.data or conc.data_programada
    if data:
        _draw(c, 706, 61.5, data.strftime("%d"))
        _draw(c, 738, 61.5, data.strftime("%m"))
        _draw(c, 768, 61.5, data.strftime("%Y"))
    for posicao, cam in enumerate(caminhoes[:SERIES_POR_FICHA], start=1):
        x0, y0, x1, y1 = _SERIE2_BOX[posicao]
        etiquetas = list(
            AnexoConcretagem.objects.filter(caminhao=cam, etapa="ETIQUETA_CP", ativo=True).order_by("criado_em", "id")
        )
        imagens = [im for im in (_imagem_etiqueta(a) for a in etiquetas) if im is not None]
        box_w, box_h = x1 - x0, y1 - y0
        if imagens:
            margem_lat, margem_topo, margem_baixo, extensao = 4, 6, 2, 6
            n = len(imagens)
            slot_w = (box_w - margem_lat * (n + 1)) / n
            slot_h = box_h - margem_topo - margem_baixo + extensao
            cursor = x0 + margem_lat
            for im in imagens:
                escala = min(slot_w / im.width, slot_h / im.height)
                w, h = im.width * escala, im.height * escala
                c.drawImage(ImageReader(im), cursor, _y(y0 + margem_topo + h), width=w, height=h,
                            preserveAspectRatio=True, mask="auto")
                cursor += slot_w + margem_lat
        else:
            texto = cam.serie_moldagem.identificacao_amostra or ""
            for i in range(3):
                linha = texto[i * 110:(i + 1) * 110]
                if linha:
                    _draw(c, x0 + 4, y0 + 16 + i * 12, linha, size=_SIZE_CAMPO_PEQUENO)


def _paginas(conc, ficha, caminhoes):
    reader = PdfReader(str(TEMPLATE_PATH))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_PAGE_W, _PAGE_H))
    _overlay_pagina1(c, conc, ficha, caminhoes)
    c.showPage()
    _overlay_pagina2(c, conc, ficha, caminhoes)
    c.showPage()
    c.save()
    buf.seek(0)
    overlay = PdfReader(buf)
    paginas = []
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        paginas.append(page)
    return paginas


def gerar_pdf(conc):
    """PDF completo da ficha (2 páginas por grupo de 5 caminhões)."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Modelo da ficha não encontrado em {TEMPLATE_PATH}")
    ficha, _ = FichaMoldagem.objects.get_or_create(concretagem=conc)
    caminhoes = list(conc.caminhoes.filter(ativo=True).select_related("serie_moldagem").order_by("ordem"))
    grupos = [caminhoes[i:i + SERIES_POR_FICHA] for i in range(0, len(caminhoes), SERIES_POR_FICHA)] or [[]]
    writer = PdfWriter()
    for grupo in grupos:
        for page in _paginas(conc, ficha, grupo):
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def nome_arquivo(conc):
    return f"FICHA DE MOLDAGEM SENAI - {conc.codigo}.pdf"


def gerar_e_anexar(conc, usuario):
    """Gera o PDF e manda ao Drive (03 Moldagem CPs), substituindo a versão anterior no sistema."""
    conteudo = gerar_pdf(conc)
    conc.anexos.filter(etapa="FICHA_MOLDAGEM", ativo=True).update(ativo=False)
    return drive.criar_anexo(
        conc, "FICHA_MOLDAGEM", conteudo, usuario, nome=nome_arquivo(conc), conteudo_tipo="application/pdf",
    )


def _gerar_por_id(conc_id, usuario_id):
    from django.contrib.auth import get_user_model

    from obras.models import Concretagem

    conc = Concretagem.objects.select_related("obra", "concreteira").get(pk=conc_id)
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    gerar_e_anexar(conc, usuario)


def agendar_geracao(conc, usuario):
    """Gera a ficha e manda ao Drive sem prender a tela (baixar etiquetas do Drive pode demorar)."""
    drive.em_segundo_plano(_gerar_por_id, conc.pk, getattr(usuario, "pk", None))
