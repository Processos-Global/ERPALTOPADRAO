from django.urls import path
from obras import views
from obras.views import vistoria_cautelar as cautelar
from obras.views import concretagem as conc

app_name = "obras"
urlpatterns = [
    path("vistorias/cautelares/", cautelar.cautelares_lista, name="cautelares_lista"),
    path("vistorias/cautelares/nova/", cautelar.cautelar_nova, name="cautelar_nova"),
    path("vistorias/cautelares/<int:pk>/", cautelar.cautelar_detalhe, name="cautelar_detalhe"),
    path("vistorias/cautelares/<int:pk>/salvar/", cautelar.cautelar_salvar, name="cautelar_salvar"),
    path("vistorias/cautelares/<int:pk>/ocorrencia/", cautelar.cautelar_ocorrencia, name="cautelar_ocorrencia"),
    path("vistorias/cautelares/<int:pk>/ocorrencia/<int:oid>/excluir/", cautelar.cautelar_ocorrencia_excluir, name="cautelar_ocorrencia_excluir"),
    path("vistorias/cautelares/<int:pk>/foto/", cautelar.cautelar_foto, name="cautelar_foto"),
    path("vistorias/cautelares/<int:pk>/pdf/", cautelar.cautelar_pdf, name="cautelar_pdf"),
    path("pos-obra/liberacoes/", __import__("obras.views.pos_obra",fromlist=["liberacoes"]).liberacoes, name="pos_obra_liberacoes"),
    path("pos-obra/<int:obra_id>/liberar/", __import__("obras.views.pos_obra",fromlist=["liberar"]).liberar, name="pos_obra_liberar"),
    path("", views.menu, name="menu"),

    path("vistorias/", views.vistorias_lista, name="vistorias_lista"),
    path("vistorias/<int:atividade_id>/alterar/", views.vistoria_alterar, name="vistoria_alterar"),

    path("fvs/", views.fvs_lista, name="fvs_lista"),
    path("fvs/nova/", views.fvs_nova, name="fvs_nova"),
    path("fvs/ambientes/", views.fvs_ambientes, name="fvs_ambientes"),
    path("fvs/<int:pk>/", views.fvs_detalhe, name="fvs_detalhe"),
    path("fvs/<int:pk>/enviar-aprovacao/", views.fvs_enviar_aprovacao, name="fvs_enviar_aprovacao"),
    path("fvs/<int:pk>/decidir/", views.fvs_decidir, name="fvs_decidir"),

    path("fichas/", views.fichas_tecnicas, name="fichas_tecnicas"),
    path("fichas/<int:obra_id>/", views.ficha_tecnica, name="ficha_tecnica"),
    path("fichas/<int:obra_id>/acao/", views.ficha_tecnica_acao, name="ficha_tecnica_acao"),

    path("almoxarifado/", views.almoxarifado_dashboard, name="almoxarifado_dashboard"),
    path("almoxarifado/<int:obra_id>/", views.almoxarifado_obra, name="almoxarifado_obra"),
    path("almoxarifado/<int:obra_id>/saida/", views.saida_estoque, name="saida_estoque"),
    path("almoxarifado/<int:obra_id>/relatorio-transferencias/", views.relatorio_transferencias, name="relatorio_transferencias"),
    path("almoxarifado/<int:obra_id>/transferencia/", views.transferencia_estoque, name="transferencia_estoque"),

    path("diario/", views.diario_lista, name="diario_lista"),
    path("diario/novo/", views.diario_novo, name="diario_novo"),
    # Mantido para links antigos já salvos/favoritados.
    path("diario/<int:obra_id>/novo/", views.diario_novo, name="diario_novo_obra"),
    path("diario/registro/<int:diario_id>/editar/", views.diario_editar, name="diario_editar"),

    # Concretagem
    path("concretagem/", conc.painel.painel, name="concretagem_painel"),
    path("concretagem/obra/<int:obra_id>/", conc.painel.obra, name="concretagem_obra"),
    path("concretagem/obra/<int:obra_id>/locais/", conc.locais.locais, name="concretagem_locais"),
    path("concretagem/obra/<int:obra_id>/locais/salvar/", conc.locais.local_salvar, name="concretagem_local_criar"),
    path("concretagem/obra/<int:obra_id>/locais/<int:pk>/salvar/", conc.locais.local_salvar, name="concretagem_local_editar"),
    path("concretagem/obra/<int:obra_id>/locais/<int:pk>/alternar/", conc.locais.local_alternar, name="concretagem_local_alternar"),
    path("concretagem/obra/<int:obra_id>/locais/api/", conc.locais.api_locais, name="concretagem_api_locais"),
    path("concretagem/nova/", conc.solicitacao.nova, name="concretagem_nova"),
    path("concretagem/<int:pk>/", conc.solicitacao.detalhe, name="concretagem_detalhe"),
    path("concretagem/<int:pk>/editar/", conc.solicitacao.editar, name="concretagem_editar"),
    path("concretagem/<int:pk>/solicitar/", conc.solicitacao.solicitar, name="concretagem_solicitar"),
    path("concretagem/<int:pk>/bombista/", conc.solicitacao.salvar_bombista, name="concretagem_bombista"),
    path("concretagem/<int:pk>/registrar-envio/", conc.solicitacao.registrar_envio, name="concretagem_registrar_envio"),
    path("concretagem/<int:pk>/enviar-email/", conc.solicitacao.enviar_email, name="concretagem_enviar_email"),
    path("concretagem/<int:pk>/aceitar/", conc.solicitacao.aceitar_manual, name="concretagem_aceitar_manual"),
    path("concretagem/<int:pk>/reagendar/", conc.solicitacao.reagendar, name="concretagem_reagendar"),
    path("concretagem/<int:pk>/cancelar/", conc.solicitacao.cancelar, name="concretagem_cancelar"),
    path("concretagem/<int:pk>/drive/", conc.solicitacao.criar_pasta_drive, name="concretagem_drive"),
    # Execução em campo
    path("concretagem/<int:pk>/caminhoes/novo/", conc.execucao.caminhao_salvar, name="concretagem_caminhao_criar"),
    path("concretagem/<int:pk>/caminhoes/<int:caminhao_pk>/salvar/", conc.execucao.caminhao_salvar, name="concretagem_caminhao_editar"),
    path("concretagem/<int:pk>/caminhoes/<int:caminhao_pk>/nf/", conc.execucao.caminhao_nf, name="concretagem_caminhao_nf"),
    path("concretagem/<int:pk>/caminhoes/<int:caminhao_pk>/remover/", conc.execucao.caminhao_remover, name="concretagem_caminhao_remover"),
    path("concretagem/<int:pk>/usos/novo/", conc.execucao.uso_salvar, name="concretagem_uso_criar"),
    path("concretagem/<int:pk>/usos/<int:uso_pk>/salvar/", conc.execucao.uso_salvar, name="concretagem_uso_editar"),
    path("concretagem/<int:pk>/usos/<int:uso_pk>/remover/", conc.execucao.uso_remover, name="concretagem_uso_remover"),
    path("concretagem/<int:pk>/sobras/nova/", conc.execucao.sobra_salvar, name="concretagem_sobra_criar"),
    path("concretagem/<int:pk>/sobras/<int:sobra_pk>/salvar/", conc.execucao.sobra_salvar, name="concretagem_sobra_editar"),
    path("concretagem/<int:pk>/sobras/<int:sobra_pk>/remover/", conc.execucao.sobra_remover, name="concretagem_sobra_remover"),
    path("concretagem/<int:pk>/finalizar/", conc.execucao.finalizar, name="concretagem_finalizar"),
    # Moldagem
    path("concretagem/<int:pk>/ficha/cabecalho/", conc.execucao.ficha_cabecalho_salvar, name="concretagem_ficha_cabecalho"),
    path("concretagem/<int:pk>/ficha/serie/<int:caminhao_pk>/", conc.execucao.serie_salvar, name="concretagem_serie_salvar"),
    path("concretagem/<int:pk>/ficha/pdf/", conc.execucao.ficha_pdf, name="concretagem_ficha_pdf"),
    path("concretagem/<int:pk>/ficha/enviar-drive/", conc.execucao.ficha_enviar_drive, name="concretagem_ficha_drive"),
    # Controle tecnológico
    path("concretagem/<int:pk>/cps-enviados/", conc.execucao.cps_enviados, name="concretagem_cps_enviados"),
    path("concretagem/<int:pk>/voltar-etapa/", conc.execucao.voltar_etapa, name="concretagem_voltar_etapa"),
    path("concretagem/<int:pk>/laudos/salvar/", conc.execucao.laudo_salvar, name="concretagem_laudo_salvar"),
    path("concretagem/<int:pk>/concluir/", conc.execucao.concluir, name="concretagem_concluir"),
    # Anexos
    path("concretagem/<int:pk>/anexos/status/", conc.anexos.anexos_status, name="concretagem_anexos_status"),
    path("concretagem/<int:pk>/anexos/reenviar/", conc.anexos.reenviar_pendentes, name="concretagem_anexos_reenviar"),
    path("concretagem/<int:pk>/anexos/<int:anexo_pk>/", conc.anexos.anexo_abrir, name="concretagem_anexo_abrir"),
    path("concretagem/<int:pk>/drive/<str:etapa>/", conc.anexos.pasta_drive, name="concretagem_pasta_drive"),
    path("concretagem/<int:pk>/ficha/serie/<int:caminhao_pk>/etiqueta/", conc.execucao.etiqueta_enviar, name="concretagem_etiqueta_enviar"),
    path("concretagem/<int:pk>/anexos/<int:anexo_pk>/miniatura/", conc.anexos.anexo_miniatura, name="concretagem_anexo_miniatura"),
    path("concretagem/<int:pk>/anexos/<int:anexo_pk>/remover/", conc.anexos.anexo_remover, name="concretagem_anexo_remover"),
    # Mapa e formatos
    path("concretagem/mapa/", conc.mapa.mapa_inicio, name="concretagem_mapa_inicio"),
    path("concretagem/obra/<int:obra_id>/mapa/", conc.mapa.mapa, name="concretagem_mapa"),
    path("concretagem/obra/<int:obra_id>/mapa/<int:local_id>/definir/", conc.mapa.mapa_definir, name="concretagem_mapa_definir"),
    path("concretagem/obra/<int:obra_id>/mapa/<int:local_id>/pintar/", conc.mapa.mapa_pintar, name="concretagem_mapa_pintar"),
    path("concretagem/formatos/", conc.mapa.formatos, name="concretagem_formatos"),
    path("concretagem/formatos/novo/", conc.mapa.formato_editor, name="concretagem_formato_novo"),
    path("concretagem/formatos/<int:pk>/editar/", conc.mapa.formato_editor, name="concretagem_formato_editar"),
    path("concretagem/formatos/<int:pk>/remover/", conc.mapa.formato_desativar, name="concretagem_formato_remover"),
    # Agenda, indicadores e diário
    path("concretagem/agenda/", conc.relatorios.agenda, name="concretagem_agenda"),
    path("concretagem/indicadores/", conc.relatorios.indicadores, name="concretagem_indicadores"),
    path("concretagem/api/do-dia/", conc.relatorios.api_concretagens_dia, name="concretagem_api_dia"),
    # Pública (sem login): resposta da concreteira pelo token.
    path("concretagem/resposta/<uuid:token>/", conc.publica.publica, name="concretagem_publica"),
]
