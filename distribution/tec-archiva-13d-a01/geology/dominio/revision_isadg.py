"""Revisión técnica local; nunca equivale a certificación archivística completa."""
from dataclasses import dataclass,asdict
from datetime import date
from collections import Counter
from geology.dominio.campos_isadg import tiene_marca

DEVUELVE='DEVUELVE'
REVISE='REVISE'


@dataclass(frozen=True)
class Hallazgo:
    gravedad:str
    regla:str
    unidad:str
    nivel:str
    que_pasa:str
    como_se_arregla:str='Revisión humana con el expediente y la TVD.'

    def como_dict(self): return asdict(self)


def contexto_de(db,renglones):
    # No declara que la base contenga evidencia certificada; no consulta ni modifica DB.
    return {'alcance':'reglas técnicas locales','revision_archivistica_pendiente':True}


def revisar(renglones,contexto=None):
    filas=list(renglones); salida=[]; vistos=set()
    if not filas: salida.append(Hallazgo(REVISE,'SIN_UNIDADES','','','No hay unidades revisables.'))
    for r in filas:
        unidad=str(r['codigo_referencia'] or r['carpeta'] or '')
        for clave in ('codigo_referencia','titulo','volumen','norma'):
            if not str(r[clave] or '').strip(): salida.append(Hallazgo(DEVUELVE,'OBLIGATORIO',unidad,r.nivel,f'Falta {clave}.'))
        if unidad in vistos: salida.append(Hallazgo(DEVUELVE,'CODIGO_DUPLICADO',unidad,r.nivel,'Código de referencia repetido.'))
        vistos.add(unidad)
        for clave,valor in r.campos.items():
            if tiene_marca(valor): salida.append(Hallazgo(DEVUELVE,'PROPUESTA_PENDIENTE',unidad,r.nivel,f'{clave} contiene propuesta sin revisión.'))
        try:
            fi,ff=r['fecha_inicial'],r['fecha_final']
            if fi and ff and date.fromisoformat(str(fi))>date.fromisoformat(str(ff)):
                salida.append(Hallazgo(DEVUELVE,'FECHAS_INVERTIDAS',unidad,r.nivel,'Fechas extremas invertidas.'))
        except ValueError:
            salida.append(Hallazgo(REVISE,'FECHAS_NO_COMPLETAS',unidad,r.nivel,'Fechas no comparables sin interpretación.'))
        salida.append(Hallazgo(REVISE,'REVISION_ARCHIVISTICA_PENDIENTE',unidad,r.nivel,
            'La comprobación técnica no certifica contenido, jerarquía, TVD ni aprobación humana.'))
    return salida


def resumen(hallazgos):
    hallazgos=list(hallazgos); c=Counter(h.gravedad for h in hallazgos)
    return {'fecha':date.today().isoformat(),'devuelve':c[DEVUELVE],'revise':c[REVISE],
        'unidades_con_problema':len({h.unidad for h in hallazgos}),
        'se_puede_entregar':False,'revision_pendiente':True}
