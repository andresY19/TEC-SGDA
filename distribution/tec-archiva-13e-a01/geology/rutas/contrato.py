"""
Contrato 733 de 2026: control del contrato, documentos editables y proceso de eliminación.

Quién puede qué:
  - La administradora ve y edita todo: parámetros, lotes, obligaciones, observaciones,
    documentos (todos los bloques) y el proceso de eliminación.
  - La líder ve el tablero, los documentos y la eliminación, sin editar.
  - Los demás perfiles y la entidad no entran aquí.

Los documentos se guardan como bloques (títulos, párrafos, listas, tablas, láminas) y salen en
Word, presentación o Excel. Nada se elimina por sí solo: la plataforma propone y una persona decide.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from geology.dominio import cobro as cb
from geology.dominio import contrato as ct
from geology.dominio import documentos as doc
from geology.dominio import eliminacion as el
from geology.dominio.estados import Rol, Usuario
from geology.modelos import (DocumentoContrato, ItemEliminacion, LoteContrato, ObligacionContrato,
                             ObservacionSupervision, PagoContrato, ProcesoEliminacion)
from geology.nucleo.bd import obtener_sesion
from geology.rutas.cuentas import usuario_actual

router = APIRouter(prefix="/contrato", tags=["Contrato"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ver(q: Usuario) -> None:
    if q.rol not in (Rol.ADMINISTRADORA, Rol.LIDER):
        raise HTTPException(403, "El módulo del contrato lo ven la administradora y la líder.")


def _admin(q: Usuario) -> None:
    if q.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Editar el contrato y sus documentos lo hace la administradora.")


def _nombre_archivo(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", texto).strip("_")[:90] or "documento"


# ---------------------------------------------------------------------------------------
# Resumen y parámetros
# ---------------------------------------------------------------------------------------
@router.get("/resumen", summary="Tablero del contrato: metros lineales, plazos, garantías y alertas")
def resumen(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ver(quien)
    r = ct.resumen(db)
    db.commit()
    return r


@router.get("/parametros", summary="Valores del contrato que se pueden corregir")
def parametros(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _ver(quien)
    p = ct.parametros(db)
    return [{"clave": k, "etiqueta": v[0], "valor": p[k], "original": v[1]} for k, v in ct.PARAMETROS.items()]


class ParametroIn(BaseModel):
    valor: str


@router.put("/parametros/{clave}", summary="Corregir un valor del contrato")
def poner_parametro(clave: str, datos: ParametroIn, db: Session = Depends(obtener_sesion),
                    quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    try:
        ct.guardar_parametro(db, clave, datos.valor)
    except ValueError as e:
        raise HTTPException(422, str(e) or "Valor no válido.")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------------------
class LoteIn(BaseModel):
    nombre: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    meta_ml: float | None = Field(default=None, ge=0, le=5000)
    recibido_en: date | None = None
    facturado_en: date | None = None
    valor_facturado: float | None = Field(default=None, ge=0)
    nota: str | None = None
    limpiar_recibo: bool = False
    limpiar_factura: bool = False


@router.put("/lotes/{numero}", summary="Ajustar un lote: metas, fechas, recibo a satisfacción y factura")
def poner_lote(numero: int, d: LoteIn, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    ct.sembrar(db)
    lt = db.query(LoteContrato).filter(LoteContrato.numero == numero).first()
    if not lt:
        raise HTTPException(404, "No existe ese lote.")
    for campo in ("nombre", "fecha_inicio", "fecha_fin", "meta_ml", "nota"):
        v = getattr(d, campo)
        if v is not None:
            setattr(lt, campo, v)
    if d.recibido_en or d.limpiar_recibo:
        lt.recibido_en = None if d.limpiar_recibo else d.recibido_en
    if d.facturado_en is not None or d.valor_facturado is not None or d.limpiar_factura:
        if d.limpiar_factura:
            lt.facturado_en, lt.valor_facturado = None, None
        else:
            if d.facturado_en is not None:
                lt.facturado_en = d.facturado_en
            if d.valor_facturado is not None:
                lt.valor_facturado = d.valor_facturado
    if lt.fecha_fin < lt.fecha_inicio:
        raise HTTPException(422, "La fecha final no puede ser anterior a la inicial.")
    db.commit()
    return {"ok": True}


class LoteNuevo(BaseModel):
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    meta_ml: float = Field(ge=0, le=5000)


@router.post("/lotes", summary="Agregar un lote")
def nuevo_lote(d: LoteNuevo, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    ct.sembrar(db)
    if d.fecha_fin < d.fecha_inicio:
        raise HTTPException(422, "La fecha final no puede ser anterior a la inicial.")
    n = (db.query(LoteContrato.numero).order_by(LoteContrato.numero.desc()).first() or (0,))[0] + 1
    db.add(LoteContrato(numero=n, nombre=d.nombre, fecha_inicio=d.fecha_inicio, fecha_fin=d.fecha_fin, meta_ml=d.meta_ml))
    db.commit()
    return {"ok": True, "numero": n}


@router.post("/lotes/al-cronograma", summary="Pasar los lotes al cronograma de seguimiento como hitos")
def lotes_al_cronograma(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    """Crea un hito por lote en el cronograma de Seguimiento (los que ya existan por nombre no se repiten)."""
    _admin(quien)
    from geology.modelos import HitoCronograma
    ct.sembrar(db)
    p = ct.parametros(db)
    por_caja = float(p["ml_por_caja"]) or 0.25
    ya = {n for (n,) in db.query(HitoCronograma.nombre).all()}
    creados = 0
    for lt in db.query(LoteContrato).order_by(LoteContrato.numero).all():
        nombre = f"{lt.nombre} · {lt.meta_ml:g} ML"
        if nombre in ya:
            continue
        db.add(HitoCronograma(nombre=nombre, periodo="", fecha_inicio=lt.fecha_inicio, fecha_fin=lt.fecha_fin,
                              meta_carpetas=None, estado_meta="Descripción validada"))
        creados += 1
    db.commit()
    return {"creados": creados, "nota": "Los hitos quedan sin meta de carpetas: fíjela en Seguimiento al repartir "
                                       f"el trabajo (un metro lineal equivale a {1 / por_caja:g} cajas)."}


# ---------------------------------------------------------------------------------------
# Obligaciones
# ---------------------------------------------------------------------------------------
@router.get("/obligaciones", summary="Las 19 obligaciones específicas y su estado")
def obligaciones(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _ver(quien)
    ct.sembrar(db)
    db.commit()
    por = {o.numero: o for o in db.query(ObligacionContrato).all()}
    salida = []
    for n, nombre, texto in ct.OBLIGACIONES:
        o = por.get(n)
        salida.append({"numero": n, "nombre": nombre, "texto": texto, "estado": o.estado if o else "pendiente",
                       "evidencia": (o.evidencia if o else "") or "", "actualizado_por": o.actualizado_por if o else None,
                       "actualizado_en": o.actualizado_en.isoformat() if o and o.actualizado_en else None,
                       "indicador": ct.indicador_de_obligacion(db, n) or ""})
    return salida


class ObligacionIn(BaseModel):
    estado: str
    evidencia: str | None = None


@router.put("/obligaciones/{numero}", summary="Marcar el estado de una obligación")
def poner_obligacion(numero: int, d: ObligacionIn, db: Session = Depends(obtener_sesion),
                     quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    if d.estado not in ("pendiente", "en_curso", "cumplida"):
        raise HTTPException(422, "El estado es pendiente, en_curso o cumplida.")
    ct.sembrar(db)
    o = db.get(ObligacionContrato, numero)
    if not o:
        raise HTTPException(404, "No existe esa obligación.")
    o.estado, o.actualizado_por, o.actualizado_en = d.estado, quien.nombre, datetime.now()
    if d.evidencia is not None:
        o.evidencia = d.evidencia
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# Observaciones de la supervisión
# ---------------------------------------------------------------------------------------
def _obs(o: ObservacionSupervision) -> dict:
    hoy = date.today()
    return {"id": o.id, "fecha": o.fecha.isoformat(), "origen": o.origen, "lote": o.lote, "descripcion": o.descripcion,
            "carpetas": o.carpetas or "", "responsable": o.responsable or "", "fecha_limite": o.fecha_limite.isoformat(),
            "estado": o.estado, "respuesta": o.respuesta or "", "cerrada_en": o.cerrada_en.isoformat() if o.cerrada_en else None,
            "vencida": o.estado == "abierta" and o.fecha_limite < hoy,
            "dias_para_vencer": (o.fecha_limite - hoy).days if o.estado == "abierta" else None}


@router.get("/observaciones", summary="Observaciones de la supervisión")
def observaciones(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _ver(quien)
    filas = db.query(ObservacionSupervision).order_by(ObservacionSupervision.estado, ObservacionSupervision.fecha_limite).all()
    return [_obs(o) for o in filas]


class ObservacionIn(BaseModel):
    fecha: date | None = None
    origen: str = "muestreo"
    lote: int | None = None
    descripcion: str = Field(min_length=3)
    carpetas: str | None = None
    responsable: str | None = None


@router.post("/observaciones", summary="Registrar una observación; el plazo corre en días hábiles")
def nueva_observacion(d: ObservacionIn, db: Session = Depends(obtener_sesion),
                      quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    p = ct.parametros(db)
    f = d.fecha or date.today()
    limite = ct.sumar_habiles(f, int(p["dias_ajuste"]))
    o = ObservacionSupervision(fecha=f, origen=d.origen, lote=d.lote, descripcion=d.descripcion, carpetas=d.carpetas,
                               responsable=d.responsable, fecha_limite=limite, creado_por=quien.nombre)
    db.add(o)
    db.commit()
    return {"id": o.id, "fecha_limite": limite.isoformat()}


class ObservacionCambio(BaseModel):
    estado: str | None = None
    respuesta: str | None = None
    responsable: str | None = None
    descripcion: str | None = None
    fecha_limite: date | None = None


@router.put("/observaciones/{oid}", summary="Responder, cerrar o ajustar una observación")
def cambiar_observacion(oid: int, d: ObservacionCambio, db: Session = Depends(obtener_sesion),
                        quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    o = db.get(ObservacionSupervision, oid)
    if not o:
        raise HTTPException(404, "No existe esa observación.")
    if d.estado is not None:
        if d.estado not in ("abierta", "corregida", "cerrada"):
            raise HTTPException(422, "El estado es abierta, corregida o cerrada.")
        o.estado = d.estado
        o.cerrada_en = date.today() if d.estado == "cerrada" else None
    for campo in ("respuesta", "responsable", "descripcion", "fecha_limite"):
        v = getattr(d, campo)
        if v is not None:
            setattr(o, campo, v)
    db.commit()
    return {"ok": True}


@router.delete("/observaciones/{oid}", summary="Quitar una observación registrada por error")
def quitar_observacion(oid: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    o = db.get(ObservacionSupervision, oid)
    if not o:
        raise HTTPException(404, "No existe esa observación.")
    db.delete(o)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------------------
TIPOS = {
    "informe_mensual": "Informe mensual",
    "informe_lote": "Informe de lote",
    "ficha": "Ficha técnica",
    "informe_final": "Informe técnico final",
    "elim_fuid": "FUID de eliminación",
    "elim_informe": "Informe de eliminación",
    "elim_presentacion": "Presentación para el Comité",
    "elim_acta": "Acta de eliminación",
    "cobro_cuenta": "Cuenta de cobro (prefactura)",
    "cobro_relacion": "Relación de metros lineales",
}


def _res(d: DocumentoContrato, con_contenido: bool = False) -> dict:
    r = {"id": d.id, "tipo": d.tipo, "tipo_nombre": TIPOS.get(d.tipo, d.tipo), "titulo": d.titulo, "clave": d.clave,
         "version": d.version, "estado": d.estado, "creado_por": d.creado_por, "editado_por": d.editado_por,
         "creado_en": d.creado_en.isoformat() if d.creado_en else None,
         "editado_en": d.editado_en.isoformat() if d.editado_en else None, "proceso_id": d.proceso_id,
         "es_presentacion": d.tipo == "elim_presentacion"}
    if con_contenido:
        r["contenido"] = d.contenido
    return r


@router.get("/documentos", summary="Documentos generados")
def documentos(tipo: str = "", proceso_id: int | None = None, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _ver(quien)
    q = db.query(DocumentoContrato)
    if tipo:
        q = q.filter(DocumentoContrato.tipo == tipo)
    if proceso_id is not None:
        q = q.filter(DocumentoContrato.proceso_id == proceso_id)
    return [_res(d) for d in q.order_by(DocumentoContrato.tipo, DocumentoContrato.clave).all()]


class GenerarIn(BaseModel):
    tipo: str
    anio: int | None = None
    mes: int | None = Field(default=None, ge=1, le=12)
    lote: int | None = None
    actividad: str | None = None
    proceso_id: int | None = None
    pago: int | None = None
    rehacer: bool = False


def _construir(db: Session, g: GenerarIn) -> tuple[str, str, dict, int | None]:
    """Devuelve (título, clave, contenido, proceso)."""
    try:
        if g.tipo == "informe_mensual":
            hoy = date.today()
            a, m = g.anio or hoy.year, g.mes or hoy.month
            t, c = doc.informe_mensual(db, a, m)
            return t, f"{a}-{m:02d}", c, None
        if g.tipo == "informe_lote":
            if not g.lote:
                raise ValueError("Indique el lote.")
            t, c = doc.informe_de_lote(db, g.lote)
            return t, f"L{g.lote}", c, None
        if g.tipo == "ficha":
            if not g.lote or not g.actividad:
                raise ValueError("Indique el lote y la actividad.")
            t, c = doc.ficha_tecnica(db, g.actividad.upper(), g.lote)
            return t, f"{g.actividad.upper()}-L{g.lote}", c, None
        if g.tipo == "informe_final":
            t, c = doc.informe_final(db)
            return t, "final", c, None
        if g.tipo in ("cobro_cuenta", "cobro_relacion"):
            if not g.pago:
                raise ValueError("Indique el pago.")
            fn = cb.cuenta_de_cobro if g.tipo == "cobro_cuenta" else cb.relacion_de_metros
            t, c = fn(db, g.pago)
            return t, f"P{g.pago}", c, None
        if g.tipo.startswith("elim_"):
            if not g.proceso_id:
                raise ValueError("Indique la propuesta de eliminación.")
            pr = db.get(ProcesoEliminacion, g.proceso_id)
            if not pr:
                raise ValueError("No existe esa propuesta de eliminación.")
            fn = {"elim_fuid": el.fuid_eliminacion, "elim_informe": el.informe_eliminacion,
                  "elim_presentacion": el.presentacion_eliminacion, "elim_acta": el.acta_eliminacion}.get(g.tipo)
            if not fn:
                raise ValueError("Tipo de documento desconocido.")
            t, c = fn(db, pr)
            return t, str(pr.id), c, pr.id
    except ValueError as e:
        raise HTTPException(422, str(e))
    raise HTTPException(422, "Tipo de documento desconocido.")


@router.post("/documentos/generar", summary="Generar un documento con los datos de la plataforma")
def generar(g: GenerarIn, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Si ya hay uno del mismo tipo y clave se devuelve ese, para no perder lo que la administradora
    editó. Con «rehacer» se vuelve a calcular y se guarda como una versión nueva.
    """
    _admin(quien)
    titulo, clave, contenido, pid = _construir(db, g)
    previo = (db.query(DocumentoContrato)
                .filter(DocumentoContrato.tipo == g.tipo, DocumentoContrato.clave == clave,
                        DocumentoContrato.proceso_id.is_(pid) if pid is None else DocumentoContrato.proceso_id == pid).first())
    if previo and not g.rehacer:
        return {"id": previo.id, "nuevo": False}
    if previo:
        previo.contenido, previo.titulo = contenido, titulo
        previo.version += 1
        previo.editado_por, previo.editado_en = quien.nombre, datetime.now()
        previo.estado = "borrador"
        db.commit()
        return {"id": previo.id, "nuevo": False, "rehecho": True}
    d = DocumentoContrato(tipo=g.tipo, titulo=titulo, clave=clave, contenido=contenido, creado_por=quien.nombre, proceso_id=pid)
    db.add(d)
    db.commit()
    return {"id": d.id, "nuevo": True}


@router.post("/documentos/fichas-del-lote/{lote}", summary="Las nueve fichas técnicas de un lote")
def fichas_del_lote(lote: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    creadas, existentes = 0, 0
    for act in doc.ACTIVIDADES:
        r = generar(GenerarIn(tipo="ficha", lote=lote, actividad=act), db, quien)
        creadas += 1 if r.get("nuevo") else 0
        existentes += 0 if r.get("nuevo") else 1
    return {"creadas": creadas, "ya_existian": existentes}


def _doc(db: Session, did: int) -> DocumentoContrato:
    d = db.get(DocumentoContrato, did)
    if not d:
        raise HTTPException(404, "No existe ese documento.")
    return d


@router.get("/documentos/{did}", summary="Abrir un documento en el visor")
def abrir(did: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ver(quien)
    r = _res(_doc(db, did), True)
    r["puede_editar"] = quien.rol is Rol.ADMINISTRADORA
    return r


class GuardarIn(BaseModel):
    titulo: str | None = None
    contenido: dict
    estado: str | None = None


@router.put("/documentos/{did}", summary="Guardar lo que se editó en el visor")
def guardar(did: int, g: GuardarIn, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    d = _doc(db, did)
    try:
        d.contenido = doc.validar_bloques(g.contenido)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if g.titulo and g.titulo.strip():
        d.titulo = g.titulo.strip()[:250]
    if g.estado:
        if g.estado not in ("borrador", "firmado"):
            raise HTTPException(422, "El estado es borrador o firmado.")
        d.estado = g.estado
    d.version += 1
    d.editado_por, d.editado_en = quien.nombre, datetime.now()
    db.commit()
    return {"ok": True, "version": d.version}


@router.delete("/documentos/{did}", summary="Quitar un documento generado (se puede volver a generar)")
def quitar_documento(did: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    d = _doc(db, did)
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.get("/documentos/{did}/descargar", summary="Descargar en Word, presentación o Excel")
def descargar(did: int, formato: str = Query("docx", pattern="^(docx|pptx|xlsx|fuid|oficial)$"),
              db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> Response:
    _ver(quien)
    d = _doc(db, did)
    sub = f"{ct.parametros(db)['contrato_numero']} · {d.titulo}"
    nombre = _nombre_archivo(d.titulo)
    try:
        if formato == "docx":
            return Response(doc.a_docx(d.titulo, d.contenido, sub), media_type=DOCX,
                            headers={"Content-Disposition": f'attachment; filename="{nombre}.docx"'})
        if formato == "pptx":
            return Response(doc.a_pptx(d.titulo, d.contenido, sub), media_type=PPTX,
                            headers={"Content-Disposition": f'attachment; filename="{nombre}.pptx"'})
        if formato == "fuid":
            if d.tipo != "elim_fuid" or not d.proceso_id:
                raise HTTPException(422, "La plantilla oficial del FUID aplica al FUID de eliminación.")
            pr = db.get(ProcesoEliminacion, d.proceso_id)
            return Response(el.fuid_a_xlsx_oficial(d.contenido, pr), media_type=XLSX,
                            headers={"Content-Disposition": f'attachment; filename="{nombre}_formato_oficial.xlsx"'})
        if formato == "oficial":
            if d.tipo != "elim_acta" or not d.proceso_id:
                raise HTTPException(422, "El formato oficial aplica al acta de eliminación (F-GDM-004).")
            pr = db.get(ProcesoEliminacion, d.proceso_id)
            return Response(el.acta_a_xlsx_oficial(d.contenido, pr), media_type=XLSX,
                            headers={"Content-Disposition": f'attachment; filename="F-GDM-004_{nombre}.xlsx"'})
        return Response(doc.a_xlsx(d.titulo, d.contenido), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'})
    except ValueError as e:
        raise HTTPException(422, str(e))
    except FileNotFoundError as e:
        raise HTTPException(500, str(e))
    except ImportError:
        raise HTTPException(500, "Falta instalar python-docx y python-pptx en el servidor (docker compose up -d --build).")


# ---------------------------------------------------------------------------------------
# Eliminación documental
# ---------------------------------------------------------------------------------------
def _proceso(db: Session, pid: int) -> ProcesoEliminacion:
    pr = db.get(ProcesoEliminacion, pid)
    if not pr:
        raise HTTPException(404, "No existe esa propuesta de eliminación.")
    return pr


def _pres(db: Session, pr: ProcesoEliminacion) -> dict:
    from sqlalchemy import func
    cuentas = dict(db.query(ItemEliminacion.estado, func.count(ItemEliminacion.id))
                   .filter(ItemEliminacion.proceso_id == pr.id).group_by(ItemEliminacion.estado).all())
    f = lambda x: x.isoformat() if x else None   # noqa: E731
    est = el.estado_de(db, pr)
    return {"id": pr.id, "nombre": pr.nombre, "estado": est, "estado_nombre": dict(el.ESTADOS).get(est, est),
            "metodo": pr.metodo or "", "fecha_sustentacion": f(pr.fecha_sustentacion), "acta_comite": pr.acta_comite or "",
            "fecha_aprobacion": f(pr.fecha_aprobacion), "publicacion_inicio": f(pr.publicacion_inicio),
            "hubo_observaciones": pr.hubo_observaciones, "concepto_solicitado": f(pr.concepto_solicitado),
            "concepto_recibido": f(pr.concepto_recibido), "fecha_eliminacion": f(pr.fecha_eliminacion),
            "acta_publicada": f(pr.acta_publicada), "nota": pr.nota or "", "plazos": el.plazos(pr),
            "items": {"propuesta": cuentas.get("propuesta", 0), "confirmada": cuentas.get("confirmada", 0),
                      "excluida": cuentas.get("excluida", 0)}}


@router.get("/eliminacion", summary="Propuestas de eliminación")
def eliminaciones(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ver(quien)
    return {"procesos": [_pres(db, pr) for pr in db.query(ProcesoEliminacion).order_by(ProcesoEliminacion.id).all()],
            "estados": [list(e) for e in el.ESTADOS]}


class ProcesoIn(BaseModel):
    nombre: str = Field(min_length=3)


@router.post("/eliminacion", summary="Crear una propuesta de eliminación")
def crear_eliminacion(d: ProcesoIn, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    pr = ProcesoEliminacion(nombre=d.nombre.strip(), creado_por=quien.nombre)
    db.add(pr)
    db.commit()
    return {"id": pr.id}


class ProcesoCambio(BaseModel):
    nombre: str | None = None
    metodo: str | None = None
    fecha_sustentacion: date | None = None
    acta_comite: str | None = None
    fecha_aprobacion: date | None = None
    publicacion_inicio: date | None = None
    hubo_observaciones: bool | None = None
    concepto_solicitado: date | None = None
    concepto_recibido: date | None = None
    fecha_eliminacion: date | None = None
    acta_publicada: date | None = None
    nota: str | None = None
    borrar: list[str] = []


_FECHAS = ("fecha_sustentacion", "fecha_aprobacion", "publicacion_inicio", "concepto_solicitado",
           "concepto_recibido", "fecha_eliminacion", "acta_publicada")


@router.put("/eliminacion/{pid}", summary="Registrar los hitos del procedimiento")
def cambiar_eliminacion(pid: int, d: ProcesoCambio, db: Session = Depends(obtener_sesion),
                        quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    pr = _proceso(db, pid)
    for campo in ("nombre", "metodo", "acta_comite", "nota", "hubo_observaciones") + _FECHAS:
        v = getattr(d, campo)
        if v is not None:
            setattr(pr, campo, v)
    for campo in d.borrar:
        if campo in _FECHAS + ("hubo_observaciones",):
            setattr(pr, campo, None)
    if pr.fecha_eliminacion and not pr.concepto_recibido and pr.hubo_observaciones and pr.concepto_solicitado:
        raise HTTPException(422, "Con observaciones en la publicación, la eliminación espera el concepto del Archivo General de la Nación.")
    db.commit()
    return _pres(db, pr)


@router.delete("/eliminacion/{pid}", summary="Quitar una propuesta (solo si no tiene hitos registrados)")
def quitar_eliminacion(pid: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    pr = _proceso(db, pid)
    if any(getattr(pr, c) for c in _FECHAS):
        raise HTTPException(409, "La propuesta ya tiene hitos del procedimiento; no se puede quitar.")
    db.query(ItemEliminacion).filter(ItemEliminacion.proceso_id == pid).delete()
    db.query(DocumentoContrato).filter(DocumentoContrato.proceso_id == pid).delete()
    db.delete(pr)
    db.commit()
    return {"ok": True}


@router.post("/eliminacion/{pid}/proponer", summary="Buscar carpetas candidatas (no confirma nada)")
def proponer(pid: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    _proceso(db, pid)
    r = el.proponer(db, pid)
    db.commit()
    return r


@router.get("/eliminacion/{pid}/items", summary="Carpetas de la propuesta")
def items(pid: int, estado: str = "", limite: int = Query(500, ge=1, le=5000), pagina: int = Query(1, ge=1),
          db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ver(quien)
    _proceso(db, pid)
    todos = el.items_con_datos(db, pid, estado or None)
    ini = (pagina - 1) * limite
    return {"total": len(todos), "items": todos[ini:ini + limite],
            "ddhh": sum(1 for i in todos if i["posible_ddhh"])}


class DecidirIn(BaseModel):
    ids: list[int] = Field(min_length=1)
    estado: str
    motivo: str = ""


@router.post("/eliminacion/{pid}/decidir", summary="Confirmar o excluir carpetas de la propuesta")
def decidir(pid: int, d: DecidirIn, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    _proceso(db, pid)
    try:
        r = el.decidir(db, pid, d.ids, d.estado, d.motivo, quien.nombre)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return r


@router.get("/eliminacion/{pid}/comprobacion", summary="Lista de comprobación del procedimiento")
def comprobacion(pid: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _ver(quien)
    return el.lista_de_comprobacion(db, _proceso(db, pid))


# ---------------------------------------------------------------------------------------
# Cobro: pagos mensuales, cuenta de cobro y soportes
# ---------------------------------------------------------------------------------------
@router.get("/pagos", summary="Pagos del contrato: lo proyectado, lo que sugiere la plataforma y lo que se cobra")
def pagos(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ver(quien)
    r = cb.calcular(db)
    db.commit()
    docs = {(d.tipo, d.clave): d.id for d in db.query(DocumentoContrato).filter(
        DocumentoContrato.tipo.in_(["cobro_cuenta", "cobro_relacion", "informe_mensual"])).all()}
    for f in r["pagos"]:
        f["doc_cuenta"] = docs.get(("cobro_cuenta", f"P{f['numero']}"))
        f["doc_relacion"] = docs.get(("cobro_relacion", f"P{f['numero']}"))
        f["soportes_lista"] = cb.lista_de_soportes(db, f["numero"])
        f["estado_nombre"] = dict(cb.ESTADOS).get(f["estado"], f["estado"])
    r["estados"] = [list(e) for e in cb.ESTADOS]
    return r


class PagoIn(BaseModel):
    ml_a_cobrar: float | None = Field(default=None, ge=0, le=5000)
    usar_sugerido: bool = False
    estado: str | None = None
    periodo_desde: date | None = None
    periodo_hasta: date | None = None
    ml_proyectados: float | None = Field(default=None, ge=0)
    prefactura_enviada: date | None = None
    prefactura_aprobada: date | None = None
    recibo_satisfaccion: date | None = None
    factura_numero: str | None = None
    factura_fecha: date | None = None
    radicado_en: date | None = None
    pagado_en: date | None = None
    valor_pagado: float | None = Field(default=None, ge=0)
    nota: str | None = None
    borrar: list[str] = []


_FECHAS_PAGO = ("prefactura_enviada", "prefactura_aprobada", "recibo_satisfaccion", "factura_fecha", "radicado_en", "pagado_en")


@router.put("/pagos/{numero}", summary="Actualizar un pago: metros lineales a cobrar, fechas del trámite y estado")
def poner_pago(numero: int, d: PagoIn, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    try:
        pg = cb._pago(db, numero)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if d.usar_sugerido:
        pg.ml_a_cobrar = None
    elif d.ml_a_cobrar is not None:
        pg.ml_a_cobrar = d.ml_a_cobrar
    if d.estado is not None:
        if d.estado not in dict(cb.ESTADOS):
            raise HTTPException(422, "Estado no válido.")
        pg.estado = d.estado
    for campo in ("periodo_desde", "periodo_hasta", "ml_proyectados", "factura_numero", "valor_pagado", "nota") + _FECHAS_PAGO:
        v = getattr(d, campo)
        if v is not None:
            setattr(pg, campo, v)
    for campo in d.borrar:
        if campo in _FECHAS_PAGO + ("factura_numero", "valor_pagado"):
            setattr(pg, campo, None)
    if pg.periodo_hasta < pg.periodo_desde:
        raise HTTPException(422, "El periodo termina antes de empezar.")
    # El estado avanza solo con las fechas, a menos que la persona lo haya fijado a mano en este mismo cambio.
    if d.estado is None:
        for estado, campo in (("pagado", "pagado_en"), ("radicado", "radicado_en"), ("facturado", "factura_numero"),
                              ("aprobado", "prefactura_aprobada"), ("prefactura", "prefactura_enviada")):
            if getattr(pg, campo):
                pg.estado = estado
                break
        else:
            pg.estado = "proyectado"
    db.commit()
    return {"ok": True}


class SoporteIn(BaseModel):
    clave: str
    listo: bool


@router.put("/pagos/{numero}/soportes", summary="Marcar un soporte manual del trámite de cobro como listo")
def poner_soporte(numero: int, d: SoporteIn, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    if d.clave not in {c for c, _, auto in cb.SOPORTES if not auto}:
        raise HTTPException(422, "Ese soporte se verifica solo o no existe.")
    try:
        pg = cb._pago(db, numero)
    except ValueError as e:
        raise HTTPException(404, str(e))
    marcas = dict(pg.soportes or {})
    marcas[d.clave] = d.listo
    pg.soportes = marcas
    db.commit()
    return {"ok": True}


@router.post("/pagos/{numero}/informes-mensuales", summary="Generar los informes mensuales que faltan del periodo del pago")
def informes_del_pago(numero: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    try:
        pg = cb._pago(db, numero)
    except ValueError as e:
        raise HTTPException(404, str(e))
    creados = 0
    for a, m in cb.meses_del_periodo(pg.periodo_desde, pg.periodo_hasta):
        r = generar(GenerarIn(tipo="informe_mensual", anio=a, mes=m), db, quien)
        creados += 1 if r.get("nuevo") else 0
    return {"creados": creados}


@router.get("/pagos/{numero}/f-fin-007.xlsx", summary="F-FIN-007 prellenado con los datos del pago")
def f_fin_007(numero: int, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> Response:
    _ver(quien)
    from geology.dominio import formatos_sgc as fmt
    try:
        datos = fmt.informe_supervisor(cb.datos_f_fin_007(db, numero))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except fmt.FaltaLaPlantilla as e:
        raise HTTPException(500, str(e))
    return Response(datos, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="F-FIN-007_pago_{numero}.xlsx"'})
