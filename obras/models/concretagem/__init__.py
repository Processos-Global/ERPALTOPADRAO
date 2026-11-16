"""Models da funcionalidade Concretagem (módulo Gestão de Obras), divididos por área."""
from .locais import ContatoEmailConcreteira, EnderecoEntregaSalvo, LocalUsoObra
from .concretagem import (
    Concretagem,
    EnvioMensagemConcretagem,
    HistoricoConcretagem,
    ItemConcretagemPlanejado,
)
from .execucao import CaminhaoConcretagem, SobraConcreto, UtilizacaoConcreto
from .moldagem import FichaMoldagem, SerieMoldagem
from .laudos import LIMITES_FCK, LaudoConcretagem
from .anexos import AnexoConcretagem
from .mapa import CelulaMapa, DestinatarioEmailFormato, FormatoDesenho, MapaLocal, SolicitacaoFormato

__all__ = [
    "ContatoEmailConcreteira", "EnderecoEntregaSalvo", "LocalUsoObra",
    "Concretagem", "EnvioMensagemConcretagem", "HistoricoConcretagem",
    "ItemConcretagemPlanejado",
    "CaminhaoConcretagem", "SobraConcreto", "UtilizacaoConcreto",
    "FichaMoldagem", "SerieMoldagem",
    "LIMITES_FCK", "LaudoConcretagem",
    "AnexoConcretagem",
    "CelulaMapa", "DestinatarioEmailFormato", "FormatoDesenho", "MapaLocal", "SolicitacaoFormato",
]
