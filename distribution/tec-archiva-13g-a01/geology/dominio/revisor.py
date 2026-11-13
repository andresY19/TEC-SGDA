"""Revisor IA deshabilitado por diseño en esta distribución local."""
from geology.dominio.revision_isadg import Hallazgo,REVISE

# No se inventa un protocolo de respuestas del proveedor mientras está deshabilitado.
CAMPOS_REVISION=()


def revisar_lote(db,renglones,contexto,limite=0):
    filas=list(renglones)
    return [Hallazgo(REVISE,'REVISOR_NO_DISPONIBLE','','',
        'La revisión IA está deshabilitada; no hubo llamadas ni revisiones aprobatorias.')],{
        'revisados':0,'de':len(filas),'se_acabo_la_cuota':False,'deshabilitado':True,
        'revision_pendiente':True}
