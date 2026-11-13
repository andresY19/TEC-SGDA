"""Conteos de estados y eventos existentes; no metas ni productividad certificada."""
from dataclasses import dataclass
from datetime import date,datetime,timedelta
from collections import Counter,defaultdict
from geology.dominio.estados import Estado

LABORES={'verificar':'Hojas de control verificadas','generar_isadg':'Descripciones generadas',
         'validar_isadg':'Descripciones validadas','aprobar':'Descripciones aprobadas',
         'revisar_hoja':'Hojas revisadas','asignar_caja':'Carpetas asignadas a caja'}
PRODUCTIVAS=tuple(LABORES)


def resumir_eventos(eventos,dia):
    conteo=Counter(); personas=defaultdict(Counter)
    for t in eventos:
        if t.fecha and t.fecha.date()==dia and t.accion in LABORES:
            conteo[LABORES[t.accion]]+=1
            personas[t.usuario or 'Sin usuario registrado'][LABORES[t.accion]]+=1
    total=sum(conteo.values())
    return {'total':total,'hoy':{**dict(conteo),'Total productivo del día':total},
        'hoy_por_persona':[{'persona':n,'labores':dict(v),'total':sum(v.values())} for n,v in sorted(personas.items())],
        'alcance':'Conteo de eventos, no unidades únicas ni producción contractual certificada.'}


def _embudo(db):
    from geology.modelos import Expediente,UnidadInventario
    with db.no_autoflush:
        universo=db.query(UnidadInventario).count(); filas=db.query(Expediente).all()
        c=Counter(e.estado for e in filas)
        return universo,{'inventariadas':c[Estado.EN_INVENTARIO.value],
            'con_hoja_de_control':sum(bool(e.tramites) for e in filas),
            'descritas':sum(bool(e.titulo and e.fecha_descripcion) for e in filas),
            'validadas':sum(c[x.value] for x in (Estado.DESCRIPCION_VALIDADA,Estado.ARCHIVADO,Estado.EN_INVENTARIO)),
            'archivadas':c[Estado.ARCHIVADO.value]+c[Estado.EN_INVENTARIO.value],
            'en_caja_definitiva':sum(bool(e.caja_definitiva) for e in filas),
            'folios_registrados':sum(e.volumen_folios or 0 for e in filas),'devueltas':c[Estado.DEVUELTO.value]}


@dataclass
class Produccion:
    datos:dict
    def como_dict(self): return self.datos


def produccion(db,dia=None):
    from geology.modelos import Trazabilidad
    dia=dia or date.today()
    with db.no_autoflush: eventos=db.query(Trazabilidad).all()
    universo,embudo=_embudo(db)
    return Produccion({'fecha':dia.isoformat(),'universo':universo,'embudo':embudo,
        **resumir_eventos(eventos,dia),'acumulado_por_persona':[],
        'acumulado_no_disponible':'No se certifica atribución acumulada a personas sin definir unidad de conteo.'})


def ahora(db,minutos=15):
    from geology.modelos import Expediente,Trazabilidad
    if not 1<=minutos<=1440: raise ValueError('Ventana de actividad inválida.')
    with db.no_autoflush:
        c=Counter(e.estado for e in db.query(Expediente).all())
        desde=datetime.now()-timedelta(minutes=minutos)
        eventos=db.query(Trazabilidad).filter(Trazabilidad.fecha>=desde).all()
    gente=defaultdict(list)
    for t in eventos:
        if t.usuario and t.fecha and t.fecha>=desde: gente[t.usuario].append(t)
    return {'minutos':minutos,'trabajando':[{'persona':n,'movimientos':len(v),
        'labores':dict(Counter(LABORES.get(t.accion,t.accion) for t in v)),
        'ultimo':max(t.fecha for t in v).isoformat()} for n,v in gente.items()],
        'en_vuelo':{k:c[s.value] for k,s in {'leyendo_el_modelo':Estado.EN_PROCESAMIENTO,
        'esperando_lectura':Estado.EN_COLA,'hojas_por_revisar':Estado.HOJA_POR_REVISAR,
        'listas_para_describir':Estado.HOJA_REVISADA,'descripciones_por_validar':Estado.DESCRIPCION_POR_VALIDAR,
        'validadas_por_aprobar':Estado.DESCRIPCION_VALIDADA,'devueltas':Estado.DEVUELTO}.items()}}
