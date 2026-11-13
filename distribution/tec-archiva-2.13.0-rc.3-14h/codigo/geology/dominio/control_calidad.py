"""Hallazgos técnicos reales sin reparar datos ni certificar controles no realizados."""
from dataclasses import dataclass,asdict
from collections import Counter
from pathlib import Path
import os,tempfile,io
from openpyxl import Workbook

ERROR='error'
REVISAR='revisar'
AVISO='aviso'


@dataclass(frozen=True)
class Hallazgo:
    carpeta:str
    gravedad:str
    prueba:str
    mensaje:str
    donde:str='Ficha del expediente'
    def como_dict(self): return asdict(self)


@dataclass
class Informe:
    revisados:int
    hallazgos:list
    def resumen(self):
        return {'revisados':self.revisados,'por_prueba':dict(Counter(h.prueba for h in self.hallazgos)),
            'por_gravedad':dict(Counter(h.gravedad for h in self.hallazgos)),
            'se_puede_entregar':False,'revision_pendiente':True}


def revisar_unidad(exp):
    h=[]
    def agregar(g,p,m): h.append(Hallazgo(exp.codigo_carpeta,g,p,m))
    if exp.fecha_inicial and exp.fecha_final and exp.fecha_inicial>exp.fecha_final:
        agregar(ERROR,'FECHAS','Fecha final anterior a inicial.')
    if not exp.periodo_id or not exp.subserie_id: agregar(REVISAR,'TVD','Clasificación incompleta; revisión humana pendiente.')
    if not exp.tramites: agregar(REVISAR,'HOJA','No hay trámites registrados.')
    if getattr(exp,'diferencia_folios',None): agregar(AVISO,'FOLIOS',exp.diferencia_folios)
    from geology.dominio.estados import ESTADOS_CON_DESCRIPCION
    if getattr(exp,'estado',None) in ESTADOS_CON_DESCRIPCION:
        from geology.dominio.campos_isadg import ELEMENTOS,hallazgos
        from types import SimpleNamespace
        valores={e.clave:getattr(exp,e.clave,None) for e in ELEMENTOS}
        valores.update(tramites=exp.tramites,volumen_folios=getattr(exp,'volumen_folios',None))
        for x in hallazgos(SimpleNamespace(**valores)):
            agregar(ERROR if x['gravedad']=='bloquea' else REVISAR,'ISADG_'+x['numeral'],x['mensaje'])
    agregar(REVISAR,'NO_VERIFICADO','No se verificaron imágenes, papel, TVD convalidada ni autenticidad histórica.')
    return h


def revisar_todo(db,estado=None,limite=2000):
    from geology.modelos import Expediente
    if not 1<=limite<=20000: raise ValueError('Límite de calidad inválido.')
    with db.no_autoflush:
        q=db.query(Expediente)
        if estado: q=q.filter(Expediente.estado==estado)
        filas=q.order_by(Expediente.id).limit(limite).all()
        return Informe(len(filas),[h for e in filas for h in revisar_unidad(e)])


def informe_a_excel(informe,responsable='',destino=None):
    libro=Workbook(); h=libro.active; h.title='Hallazgos'
    h.append(['Carpeta','Gravedad','Prueba','Mensaje','Dónde'])
    for x in informe.hallazgos:
        for i,v in enumerate((x.carpeta,x.gravedad,x.prueba,x.mensaje,x.donde),1):
            celda=h.cell(h.max_row+1,i) if i==1 else h.cell(h.max_row,i)
            celda.value=v; celda.data_type='s'
    salida=io.BytesIO(); libro.save(salida); libro.close()
    # Archivo nuevo exclusivo; jamás reemplaza un informe anterior.
    fd,nombre=tempfile.mkstemp(prefix='geology-calidad-',suffix='.xlsx',dir=destino)
    with os.fdopen(fd,'wb') as f: f.write(salida.getvalue())
    return Path(nombre)
