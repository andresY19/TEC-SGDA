"""Inventario de documentos facilitativos o de apoyo (obligación 9). Ver geology/dominio/apoyo.py."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from geology.dominio import apoyo as ap
from geology.dominio import formatos_sgc as fmt
from geology.dominio.estados import Rol, Usuario
from geology.modelos import DocumentoApoyo, Expediente
from geology.nucleo.bd import obtener_sesion
from geology.rutas.cuentas import usuario_actual

router = APIRouter(prefix="/apoyo", tags=["Documentos de apoyo"])
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _puede_decidir(q: Usuario) -> None:
    if q.es_entidad or q.rol is Rol.CONSULTA:
        raise HTTPException(403, "Su perfil es de consulta y no decide sobre documentos de apoyo.")


def _exp(db: Session, codigo: str) -> Expediente:
    e = db.query(Expediente).filter(Expediente.codigo_carpeta == codigo.upper()).first()
    if not e:
        raise HTTPException(404, f"La carpeta {codigo} no está en GEOLOGY.")
    return e


@router.get("/resumen", summary="Cuántos documentos de apoyo hay y cuántos faltan por decidir")
def resumen(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _puede_decidir(quien)
    return ap.resumen(db)


@router.get("/carpeta/{codigo}", summary="Lo que la plataforma propone como apoyo en una carpeta, y lo ya decidido")
def de_la_carpeta(codigo: str, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _puede_decidir(quien)
    exp = _exp(db, codigo)
    ap.sincronizar(db, exp)
    docs = db.query(DocumentoApoyo).filter(DocumentoApoyo.codigo_carpeta == exp.codigo_carpeta).order_by(DocumentoApoyo.id).all()
    return {"carpeta": exp.codigo_carpeta, "documentos": [ap.a_dict(d) for d in docs],
            "que_hacer": ("Confirme lo que sí es un documento de apoyo o un duplicado y descarte lo que no. Confirmar solo lo "
                          "incluye en el inventario de apoyo; no saca ni elimina nada de la carpeta.")}


class NuevoApoyo(BaseModel):
    documento: str = Field(min_length=3, max_length=300)
    clase: str = Field(default="facilitativo", pattern="^(facilitativo|duplicado|otro)$")
    folio_desde: int | None = None
    folio_hasta: int | None = None
    tramite: int | None = None
    motivo: str = ""


@router.post("/carpeta/{codigo}", summary="Agregar a mano un documento de apoyo que la plataforma no vio")
def agregar(codigo: str, cuerpo: NuevoApoyo, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _puede_decidir(quien)
    exp = _exp(db, codigo)
    d = DocumentoApoyo(codigo_carpeta=exp.codigo_carpeta, tramite_no_item=cuerpo.tramite, folio_desde=cuerpo.folio_desde,
                       folio_hasta=cuerpo.folio_hasta, documento=cuerpo.documento.strip(), clase=cuerpo.clase,
                       motivo=cuerpo.motivo.strip() or "Agregado por la persona que revisó la carpeta.", estado="confirmado",
                       origen="persona", decidido_por=quien.nombre, decidido_en=datetime.now())
    db.add(d)
    db.commit()
    return ap.a_dict(d)


class Decision(BaseModel):
    estado: str = Field(pattern="^(propuesto|confirmado|descartado)$")
    clase: str | None = Field(default=None, pattern="^(facilitativo|duplicado|otro)$")
    motivo: str | None = None


@router.put("/{apoyo_id}", summary="Confirmar o descartar un documento de apoyo")
def decidir(apoyo_id: int, cuerpo: Decision, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _puede_decidir(quien)
    d = db.get(DocumentoApoyo, apoyo_id)
    if not d:
        raise HTTPException(404, "Ese documento de apoyo no existe.")
    d.estado = cuerpo.estado
    if cuerpo.clase:
        d.clase = cuerpo.clase
    if cuerpo.motivo is not None:
        d.motivo = cuerpo.motivo
    d.decidido_por, d.decidido_en = quien.nombre, datetime.now()
    db.commit()
    return ap.a_dict(d)


@router.get("/inventario.xlsx", summary="Inventario de documentos de apoyo en el formato FUID F-GDM-003")
def inventario(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    _puede_decidir(quien)
    filas = ap.filas_fuid(db)
    if not filas:
        raise HTTPException(404, "Todavía no hay documentos de apoyo confirmados. Confírmelos en la ficha de cada carpeta.")
    primera = db.query(Expediente).filter(Expediente.codigo_carpeta == filas[0]["correlativo"]).first()
    encabezado = {"entidad_remitente": "Hometic SAS", "entidad_productora": "Servicio Geológico Colombiano",
                  "unidad_administrativa": "", "oficina_productora": "",
                  "objeto": "Inventario de documentos facilitativos o de apoyo y duplicados, contrato 733 de 2026"}
    nombre = f"F-GDM-003_inventario_documentos_de_apoyo_{date.today().isoformat()}.xlsx"
    return Response(fmt.fuid(filas, encabezado), media_type=EXCEL,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
