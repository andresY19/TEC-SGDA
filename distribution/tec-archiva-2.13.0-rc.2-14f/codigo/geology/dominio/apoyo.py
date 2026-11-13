"""
Inventario de documentos facilitativos o de apoyo (obligación 9 del contrato).

El anexo técnico pide entregar el «inventario documental de aquellos documentos que son
facilitativos o de apoyo», y el plan de trabajo lo lista como «inventario de apoyo y duplicados».

Qué es un documento de apoyo. En la práctica archivística colombiana, un documento facilitativo o
de apoyo es el que sirvió para trabajar pero no es evidencia de la función de la dependencia: copias
de normas, circulares externas, publicaciones, folletos, invitaciones, borradores, formatos en
blanco, notas de cortesía. Los duplicados son copias exactas de un documento que ya está en el
expediente. Estos documentos no hacen parte de la serie y no se transfieren; se inventarían para
que la entidad sepa qué se separó y pueda decidir.

Quién decide. La plataforma lee los tipos documentales y las observaciones de los trámites de la
hoja de control y PROPONE; una persona confirma o descarta cada propuesta, o agrega a mano lo que la
plataforma no vio. Nada se separa, se saca de la carpeta ni se elimina por esta vía: es solo el
inventario. La regla de detección sale de la práctica archivística y del anexo técnico, no de un
procedimiento del Servicio Geológico, y por eso está marcada para validar con la supervisión.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

CLASES = {"facilitativo": "Facilitativo o de apoyo", "duplicado": "Duplicado o copia", "otro": "Otro"}

_REGLAS: list[tuple[str, re.Pattern, str]] = [
    ("duplicado", re.compile(r"\b(duplicad\w*|repetid\w*|fotocopi\w*|copias? (?:simple|informal|de|del|para)\b|reproducci[oó]n|"
                             r"por duplicado|copia de consulta)"),
     "Parece un duplicado o una copia de un documento que ya está en el expediente."),
    ("facilitativo", re.compile(r"\b(borrador\w*|folleto\w*|plegable\w*|tarjeta\w*|invitaci[oó]n\w*|volante\w*|bolet[ií]n\w*|"
                                r"catálogo\w*|catalogo\w*|recorte\w*|prensa|publicaci[oó]n\w*|revista\w*|"
                                r"circular(?:es)? (?:informativ\w*|externa\w*)|formato\w* en blanco|nota\w* de cortes[ií]a|"
                                r"saludo\w*|agenda\w*|material de apoyo|documento\w* de apoyo|de consulta|facilitativ\w*|"
                                r"informativ[oa]s?)\b"),
     "Parece un documento facilitativo o de apoyo, que no es evidencia de la función."),
]

_VACIOS = {"na", "n a", "no aplica", "ninguno", "ninguna", "-", "--"}


def propuestas(exp) -> list[dict]:
    """Candidatos de una carpeta, leyendo tipo documental y observaciones de cada trámite."""
    salida, vistos = [], set()
    for t in sorted(exp.tramites or [], key=lambda x: x.no_item):
        for texto in (t.tipo_documental or "", t.observaciones or ""):
            plano = texto.lower().strip()
            if not plano or plano.replace(".", "").replace("/", "") in _VACIOS:
                continue
            for clase, rx, motivo in _REGLAS:
                if rx.search(plano) and t.no_item not in vistos:
                    vistos.add(t.no_item)
                    salida.append({"tramite": t.no_item, "folio_desde": t.folio_desde, "folio_hasta": t.folio_hasta,
                                   "documento": (t.tipo_documental or "")[:300], "clase": clase, "motivo": motivo})
    return salida


def sincronizar(db: Session, exp) -> int:
    """Crea como «propuesto» lo que aún no está registrado. No toca lo ya decidido."""
    from geology.modelos import DocumentoApoyo
    existentes = {(d.tramite_no_item, d.clase) for d in
                  db.query(DocumentoApoyo).filter(DocumentoApoyo.codigo_carpeta == exp.codigo_carpeta,
                                                  DocumentoApoyo.origen == "plataforma").all()}
    nuevos = 0
    for p in propuestas(exp):
        if (p["tramite"], p["clase"]) in existentes:
            continue
        db.add(DocumentoApoyo(codigo_carpeta=exp.codigo_carpeta, tramite_no_item=p["tramite"], folio_desde=p["folio_desde"],
                              folio_hasta=p["folio_hasta"], documento=p["documento"], clase=p["clase"], motivo=p["motivo"]))
        nuevos += 1
    if nuevos:
        db.commit()
    return nuevos


def a_dict(d) -> dict:
    return {"id": d.id, "carpeta": d.codigo_carpeta, "tramite": d.tramite_no_item, "folio_desde": d.folio_desde,
            "folio_hasta": d.folio_hasta, "documento": d.documento, "clase": d.clase, "clase_nombre": CLASES.get(d.clase, d.clase),
            "motivo": d.motivo, "estado": d.estado, "origen": d.origen, "decidido_por": d.decidido_por,
            "decidido_en": d.decidido_en.isoformat(timespec="minutes") if d.decidido_en else None}


def resumen(db: Session) -> dict:
    from geology.modelos import DocumentoApoyo as D
    todos = db.query(D).all()
    por_estado = {"propuesto": 0, "confirmado": 0, "descartado": 0}
    por_clase = {}
    pendientes = set()
    for d in todos:
        por_estado[d.estado] = por_estado.get(d.estado, 0) + 1
        if d.estado == "confirmado":
            por_clase[d.clase] = por_clase.get(d.clase, 0) + 1
        if d.estado == "propuesto":
            pendientes.add(d.codigo_carpeta)
    return {"por_estado": por_estado, "confirmados_por_clase": {CLASES.get(k, k): v for k, v in por_clase.items()},
            "carpetas_con_pendientes": sorted(pendientes)}


def filas_fuid(db: Session) -> list[dict]:
    """Los documentos confirmados, en las columnas del FUID F-GDM-003."""
    from geology.modelos import DocumentoApoyo as D, Expediente, Seccion, Serie, Subserie
    filas = []
    docs = (db.query(D).filter(D.estado == "confirmado").order_by(D.codigo_carpeta, D.tramite_no_item).all())
    for i, d in enumerate(docs, start=1):
        exp = db.query(Expediente).filter(Expediente.codigo_carpeta == d.codigo_carpeta).first()
        sub = db.get(Subserie, exp.subserie_id) if exp and exp.subserie_id else None
        serie = db.get(Serie, sub.serie_id) if sub else None
        seccion = db.get(Seccion, serie.seccion_id) if serie else None
        tr = next((t for t in (exp.tramites if exp else []) if t.no_item == d.tramite_no_item), None)
        fecha = (tr.fecha.isoformat() if tr and getattr(tr, "fecha", None) else "S/F")
        folios = (d.folio_hasta - d.folio_desde + 1) if d.folio_desde and d.folio_hasta and d.folio_hasta >= d.folio_desde else 1
        filas.append({
            "orden": i,
            "codigo": ".".join(x for x in (seccion.codigo_dependencia if seccion else "", serie.codigo if serie else "",
                                           sub.codigo if sub else "") if x),
            "serie_subserie": " / ".join(x for x in (serie.nombre if serie else "", sub.nombre if sub else "") if x),
            "unidad_documental": d.documento or "(sin nombre)", "fecha_inicial": fecha, "fecha_final": fecha,
            "soporte_fisico": "X", "caja": (exp.caja_definitiva or exp.caja_trabajo or exp.caja_origen or "") if exp else "",
            "carpeta": (exp.consecutivo_en_caja or "") if exp else "", "correlativo": d.codigo_carpeta, "folios": folios,
            "publico": "X",
            "notas": f"{CLASES.get(d.clase, d.clase)}. {d.motivo or ''} Folios {d.folio_desde or '—'} a {d.folio_hasta or '—'} de la hoja de control.".strip(),
        })
    return filas
