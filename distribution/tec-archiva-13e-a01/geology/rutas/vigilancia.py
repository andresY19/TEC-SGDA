"""Edición simultánea, alertas y registro de descargas (versión 2.13.0). Ver geology/dominio/vigilancia.py."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from geology.dominio import vigilancia as vg
from geology.dominio.estados import Rol, Usuario
from geology.nucleo.bd import obtener_sesion
from geology.rutas.cuentas import usuario_actual

router = APIRouter(prefix="/vigilancia", tags=["Vigilancia"])
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Apertura(BaseModel):
    carpeta: str
    lugar: str = "hoja"


@router.post("/edicion/abrir", summary="Avisar que se abrió (o se sigue editando) una hoja o una ficha")
def abrir(cuerpo: Apertura, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    if quien.es_entidad:
        raise HTTPException(403, "Su perfil es de consulta.")
    return vg.abrir(db, quien, cuerpo.carpeta.strip().upper(), cuerpo.lugar)


@router.post("/edicion/cerrar", summary="Avisar que ya no se está editando")
def cerrar(cuerpo: Apertura, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    vg.cerrar(db, quien, cuerpo.carpeta.strip().upper(), cuerpo.lugar)
    return {"ok": True}


@router.get("/alertas", summary="Mis alertas")
def alertas(todas: bool = Query(False), db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    lista = vg.mis_alertas(db, quien.correo, solo_nuevas=not todas)
    return {"nuevas": sum(1 for a in lista if not a["leida"]), "alertas": lista}


class Leidas(BaseModel):
    ids: list[int] | None = None


@router.post("/alertas/leidas", summary="Marcar mis alertas como leídas (todas, o las indicadas)")
def leidas(cuerpo: Leidas, db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    return {"marcadas": vg.marcar_leidas(db, quien.correo, cuerpo.ids)}


def _solo_administradora(q: Usuario) -> None:
    if q.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "El registro de descargas lo consulta solo la administradora.")


@router.get("/descargas", summary="Quién descargó qué y cuándo")
def descargas(desde: date | None = None, hasta: date | None = None, correo: str | None = None,
              instrumento: str | None = None, limite: int = Query(500, le=5000),
              db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _solo_administradora(quien)
    return vg.listar_descargas(db, desde, hasta, correo, instrumento, limite)


@router.get("/descargas.xlsx", summary="El registro de descargas en Excel")
def descargas_excel(desde: date | None = None, hasta: date | None = None, correo: str | None = None,
                    instrumento: str | None = None, db: Session = Depends(obtener_sesion),
                    quien: Usuario = Depends(usuario_actual)):
    _solo_administradora(quien)
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font
    d = vg.listar_descargas(db, desde, hasta, correo, instrumento, limite=100000)
    libro = Workbook()
    h = libro.active
    h.title = "Descargas"
    cab = ["Fecha", "Persona", "Correo", "Rol", "Instrumento", "Archivo", "Filtros", "Bytes", "Dirección IP"]
    h.append(cab)
    for c in h[1]:
        c.font = Font(bold=True)
    for f in d["filas"]:
        h.append([f["fecha"].replace("T", " "), f["nombre"], f["correo"], f["rol"], f["instrumento"], f["archivo"],
                  f["filtros"], f["bytes"], f["ip"]])
    for col, ancho in zip("ABCDEFGHI", (19, 26, 30, 14, 40, 44, 40, 10, 16)):
        h.column_dimensions[col].width = ancho
    r = libro.create_sheet("Resumen")
    r.append(["Por persona", "Descargas"])
    for x in d["por_persona"]:
        r.append([x["nombre"], x["descargas"]])
    r.append([])
    r.append(["Por instrumento", "Descargas"])
    for x in d["por_instrumento"]:
        r.append([x["instrumento"], x["descargas"]])
    r.column_dimensions["A"].width = 50
    buf = io.BytesIO()
    libro.save(buf)
    return Response(buf.getvalue(), media_type=EXCEL,
                    headers={"Content-Disposition": f'attachment; filename="registro_de_descargas_{date.today().isoformat()}.xlsx"'})
