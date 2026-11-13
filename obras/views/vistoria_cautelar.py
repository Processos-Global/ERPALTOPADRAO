import io
from collections import OrderedDict

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao
from obras.models import Obra, VistoriaCautelar, OcorrenciaCautelar, FotoCautelar
from cadastros.models import ModeloVistoria


def _sections(esquema):
    result = OrderedDict()
    for c in esquema:
        result.setdefault(c['secao'], []).append({**c, 'opcoes_lista': [x for x in c.get('opcoes', '').splitlines() if x.strip()]})
    return list(result.items())


def _schema(modelo):
    return list(modelo.campos.order_by('ordem', 'pk').values('chave', 'titulo', 'tipo', 'opcoes', 'obrigatorio', 'secao'))


def _validate(vistoria, values):
    errors = []
    for field in vistoria.esquema:
        key = field['chave']
        value = values.get(key)
        if field['obrigatorio'] and not value:
            errors.append(field['titulo'])
        choices = [x.strip() for x in field.get('opcoes', '').splitlines() if x.strip()]
        if field['tipo'] == 'SIM_NAO':
            choices = ['Sim', 'Não']
        if choices and value:
            selected = value if isinstance(value, list) else [value]
            if any(x not in choices for x in selected):
                errors.append(f'Opção inválida: {field["titulo"]}')
    return errors


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def cautelares_lista(request):
    obra_id = request.GET.get('obra')
    obras = Obra.objects.filter(ativa=True).order_by('nome')
    obra = get_object_or_404(obras, pk=obra_id) if obra_id else obras.first()
    registros = VistoriaCautelar.objects.filter(obra=obra).select_related('modelo') if obra else []
    return render(request, 'obras/vistorias/cautelares_lista.html', {'obras': obras, 'obra': obra, 'registros': registros})


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def cautelar_nova(request):
    obras = Obra.objects.filter(ativa=True).order_by('nome')
    modelos = ModeloVistoria.objects.filter(ativo=True).order_by('nome')
    if request.method == 'POST':
        obra = get_object_or_404(obras, pk=request.POST.get('obra'))
        modelo = get_object_or_404(modelos, pk=request.POST.get('modelo'))
        codigo = request.POST.get('codigo', '').strip()
        if not codigo or VistoriaCautelar.objects.filter(obra=obra, codigo=codigo).exists():
            messages.error(request, 'Informe um código único para este imóvel nesta obra.')
        else:
            vistoria = VistoriaCautelar.objects.create(
                obra=obra, modelo=modelo, codigo=codigo,
                endereco=request.POST.get('endereco', '').strip(),
                posicao=request.POST.get('posicao', '').strip(),
                esquema=_schema(modelo), criado_por=request.user,
            )
            return redirect('obras:cautelar_detalhe', pk=vistoria.pk)
    return render(request, 'obras/vistorias/cautelar_nova.html', {'obras': obras, 'modelos': modelos, 'obra_id': request.GET.get('obra', '')})


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def cautelar_detalhe(request, pk):
    vistoria = get_object_or_404(VistoriaCautelar.objects.select_related('obra', 'modelo').prefetch_related('ocorrencias__fotos', 'fotos'), pk=pk)
    secoes = _sections(vistoria.esquema)
    for _, campos in secoes:
        for campo in campos:
            campo['valor'] = vistoria.respostas.get(campo['chave'], [] if campo['tipo'] == 'MULTIPLA' else '')
            campo['selecoes'] = campo['valor'] if isinstance(campo['valor'], list) else [campo['valor']]
    return render(request, 'obras/vistorias/cautelar_detalhe.html', {'vistoria': vistoria, 'secoes': secoes, 'respostas': vistoria.respostas, 'manifestacoes': MANIFESTACOES})


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def cautelar_salvar(request, pk):
    with transaction.atomic():
        v = get_object_or_404(VistoriaCautelar.objects.select_for_update(), pk=pk)
        if v.situacao != 'RASCUNHO':
            raise PermissionDenied('Vistoria finalizada não pode ser alterada.')
        data = {}
        for c in v.esquema:
            chave = c['chave']
            data[chave] = request.POST.getlist(chave) if c['tipo'] == 'MULTIPLA' else request.POST.get(chave, '').strip()
        invalid = _validate(v, data)
        if request.POST.get('finalizar') and invalid:
            messages.error(request, 'Campos obrigatórios ou opções inválidas: ' + ', '.join(invalid))
        else:
            v.respostas = data
            v.endereco = request.POST.get('endereco', v.endereco).strip()
            v.posicao = request.POST.get('posicao', v.posicao).strip()
            if request.POST.get('finalizar'):
                v.situacao = 'FINALIZADA'
                v.finalizado_em = timezone.now()
            v.save()
            messages.success(request, 'Vistoria finalizada.' if v.situacao == 'FINALIZADA' else 'Rascunho salvo.')
    return redirect('obras:cautelar_detalhe', pk=pk)


MANIFESTACOES = ['Ausência de estrutura', 'Trincas / Rachaduras', 'Recalques', 'Muro/Parede fora do prumo', 'Infiltração', 'Descolamento de revestimento', 'Pintura', 'Goteira', 'Outros']


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def cautelar_ocorrencia(request, pk):
    v = get_object_or_404(VistoriaCautelar, pk=pk)
    if v.situacao != 'RASCUNHO':
        raise PermissionDenied('Vistoria finalizada.')
    ambiente = request.POST.get('ambiente', '').strip()
    manifestacao = request.POST.get('manifestacao', '').strip()
    if not ambiente or manifestacao not in MANIFESTACOES:
        messages.error(request, 'Informe ambiente e manifestação válida.')
    else:
        OcorrenciaCautelar.objects.create(vistoria=v, ambiente=ambiente, manifestacao=manifestacao,
            elemento=request.POST.get('elemento', '').strip(), localizacao=request.POST.get('localizacao', '').strip(),
            descricao=request.POST.get('descricao', '').strip())
        messages.success(request, 'Inconformidade adicionada.')
    return redirect('obras:cautelar_detalhe', pk=pk)


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def cautelar_ocorrencia_excluir(request, pk, oid):
    v = get_object_or_404(VistoriaCautelar, pk=pk)
    if v.situacao != 'RASCUNHO':
        raise PermissionDenied('Vistoria finalizada.')
    get_object_or_404(OcorrenciaCautelar, pk=oid, vistoria=v).delete()
    return redirect('obras:cautelar_detalhe', pk=pk)


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def cautelar_foto(request, pk):
    v = get_object_or_404(VistoriaCautelar, pk=pk)
    if v.situacao != 'RASCUNHO':
        raise PermissionDenied('Vistoria finalizada.')
    ocorrencia = None
    if request.POST.get('ocorrencia'):
        ocorrencia = get_object_or_404(OcorrenciaCautelar, vistoria=v, pk=request.POST['ocorrencia'])
    for img in request.FILES.getlist('imagens'):
        if not img.content_type.startswith('image/') or img.size > 12 * 1024 * 1024:
            messages.error(request, 'Somente imagens de até 12 MB são aceitas.')
            continue
        FotoCautelar.objects.create(vistoria=v, ocorrencia=ocorrencia, imagem=img,
                                    legenda=request.POST.get('legenda', '').strip())
    return redirect('obras:cautelar_detalhe', pk=pk)


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def cautelar_pdf(request, pk):
    v = get_object_or_404(VistoriaCautelar.objects.select_related('obra', 'modelo').prefetch_related('ocorrencias', 'fotos'), pk=pk)
    if v.situacao != 'FINALIZADA':
        raise Http404('Finalize a vistoria antes de emitir o documento.')
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.utils import ImageReader
    from xml.sax.saxutils import escape
    from PIL import Image as PILImage
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=(595,842), rightMargin=43, leftMargin=43, topMargin=52, bottomMargin=50)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SaariTitle', parent=styles['Title'], textColor=colors.HexColor('#49372f'), fontSize=17, leading=22, spaceAfter=18))
    styles.add(ParagraphStyle(name='SaariSection', parent=styles['Heading2'], textColor=colors.HexColor('#6e5241'), spaceBefore=17, spaceAfter=8))
    styles['Normal'].fontSize = 9
    styles['Normal'].leading = 13
    def p(value): return Paragraph(escape(str(value or '—')).replace('\n', '<br/>'), styles['Normal'])
    story = [Paragraph('RELATÓRIO DE VISTORIA CAUTELAR DE VIZINHANÇA', styles['SaariTitle']),
             p(f'Obra: {v.obra.nome}  |  Imóvel: {v.codigo}  |  Modelo: {v.modelo.nome}'),
             p(f'Endereço: {v.endereco}  |  Posição: {v.posicao}')]
    sections = _sections(v.esquema)
    for heading, fields in sections:
        story.append(Paragraph(escape(heading), styles['SaariSection']))
        data = [[p(field['titulo']), p(', '.join(v.respostas.get(field['chave'], [])) if isinstance(v.respostas.get(field['chave']), list) else v.respostas.get(field['chave'], ''))] for field in fields]
        if data:
            table = Table(data, colWidths=[190,320], hAlign='LEFT')
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d7c9b9'))]))
            story.append(table)
    story.insert(3, Paragraph('OBJETIVO E METODOLOGIA', styles['SaariSection']))
    story.insert(4, p('Registrar as condições aparentes dos imóveis vizinhos antes do início da obra, com vistoria visual e sensorial não destrutiva, limitada aos elementos acessíveis na data da inspeção.'))
    story.append(Paragraph('ANOMALIAS / MANIFESTAÇÕES', styles['SaariSection']))
    if not v.ocorrencias.exists(): story.append(p('Nenhuma ocorrência registrada.'))
    for i, o in enumerate(v.ocorrencias.all(), 1):
        story.append(p(f'{i}. {o.ambiente} — {o.manifestacao}'))
        story.append(p(f'Elemento: {o.elemento} | Localização: {o.localizacao} | Descrição: {o.descricao}'))
    story.append(Paragraph('CONCLUSÃO E DECLARAÇÃO', styles['SaariSection']))
    story.append(p('Este registro descreve as condições aparentes encontradas na data da vistoria, não abrangendo elementos ocultos ou situações que demandem ensaios, prospecções ou investigação específica. Alterações futuras deverão ser avaliadas mediante comparação técnica.'))
    story.append(p('Declaro que autorizei a realização da vistoria cautelar no imóvel acima identificado. A assinatura comprova a declaração aqui expressa e não constitui, por si só, concordância com todas as avaliações técnicas.'))
    story.append(Spacer(1,35))
    story.append(p('__________________________________                     __________________________________'))
    story.append(p('Proprietário / Representante                                           Vistoriador responsável'))
    story.append(Paragraph('ANEXO FOTOGRÁFICO', styles['SaariSection']))
    for index, foto in enumerate(v.fotos.all(), 1):
        try:
            with foto.imagem.open('rb') as f:
                content = f.read()
            image = PILImage.open(io.BytesIO(content))
            image.verify()
            image = PILImage.open(io.BytesIO(content)).convert('RGB')
            img_buf = io.BytesIO()
            image.save(img_buf, format='JPEG', quality=82)
            img_buf.seek(0)
            w, h = image.size
            ratio = min(430/w, 300/h)
            story.append(KeepTogether([p(f'Foto {index}: {foto.legenda}'), Image(img_buf, width=w*ratio, height=h*ratio), Spacer(1,12)]))
        except (OSError, ValueError):
            story.append(p(f'Foto {index}: imagem indisponível.'))
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#8f7159'))
        canvas.line(43, 38, 552, 38)
        canvas.setFont('Helvetica',8)
        canvas.drawString(43, 25, 'SAARI ERP • Vistoria cautelar de vizinhança')
        canvas.drawRightString(552,25,f'Página {document.page}')
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=f'vistoria-cautelar-{v.pk}.pdf', content_type='application/pdf')
