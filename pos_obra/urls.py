from django.urls import path
from . import views
app_name='pos_obra'
urlpatterns=[
 path('',views.painel,name='painel'),
 path('portal/ambientes/',views.ambientes,name='portal_ambientes'),
 path('anexos/<int:pk>/publicar/',views.publicar_anexo,name='publicar_anexo'),
 path('os/<int:pk>/material/<int:item_pk>/',views.editar_material,name='editar_material'),
 path('os/',views.lista,name='lista'),
 path('kanban/',views.kanban,name='kanban'),
 path('os/nova/',views.novo,name='novo'),
 path('obras-antigas/nova/',views.obra_historica,name='obra_historica'),
 path('os/<int:pk>/',views.detalhe,name='detalhe'),
 path('os/<int:pk>/finalizar/',views.finalizar_os,name='finalizar'),
 path('os/<int:pk>/material/',views.adicionar_material,name='material'),
 path('os/<int:pk>/anexo/',views.upload,name='upload'),
 path('anexos/<int:pk>/baixar/',views.anexo,name='anexo'),
 path('os/<int:pk>/pdf/<slug:tipo>/',views.relatorio,name='relatorio'),
 path('cadastros/<slug:modelo>/',views.cadastros,name='cadastros'),
 path('cadastros/<slug:modelo>/novo/',views.cadastrar,name='cadastrar'),
 path('cadastros/<slug:modelo>/<int:pk>/editar/',views.cadastrar,name='editar'),
 path('portal/',views.portal,name='portal'),
 path('portal/novo/',views.portal_novo,name='portal_novo'),
 path('portal/os/<int:pk>/',views.portal_detalhe,name='portal_detalhe'),
 path('portal/os/<int:pk>/pdf/<slug:tipo>/',views.portal_pdf,name='portal_pdf'),
 path('portal/os/<int:pk>/pesquisa/',views.responder_pesquisa,name='pesquisa'),
]
