"""Paquete de entrega de la digitalización: copia de consulta, copia maestra, índice y acta."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from geology.dominio import division, paquete_entrega
from geology.dominio.codigos import normalizar_codigo_carpeta
from geology.dominio.estados import Estado, Rol, Usuario
from geology.dominio.publicacion import es_publicable, motivos_de_bloqueo
from geology.modelos import Archivo, Expediente
from geology.nucleo.bd import obtener_sesion
from geology.rutas import instrumentos
from geology.rutas.cuentas import usuario_actual

router = APIRouter(prefix="/entrega", tags=["Entrega"])

ENTREGABLES = (Estado.DESCRIPCION_VALIDADA.value, Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value)
MAXIMO = int(os.getenv("MAX_EXPEDIENTES_POR_ENTREGA", "40"))
SALIDA = Path("deposito/entregas")


class Seleccion(BaseModel):
    periodo: str | None = None
    caja: str | None = None
    carpetas: list[str] = []
    incluir_maestra: bool = True


def _solo_administradora(quien: Usuario) -> None:
    if quien.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "La entrega formal la genera la administradora.")


def _seleccionar(db: Session, s: Seleccion):
    if s.carpetas:
        codigos = [normalizar_codigo_carpeta(c) or c.upper() for c in s.carpetas]
        filas = db.query(Expediente).filter(Expediente.codigo_carpeta.in_(codigos)).all()
        faltan = set(codigos) - {e.codigo_carpeta for e in filas}
    else:
        filas = instrumentos._expedientes(db, list(ENTREGABLES), s.caja, s.periodo)
        faltan = set()
    incluibles, excluidas = [], [{"codigo": c, "motivo": "no existe"} for c in sorted(faltan)]
    for e in filas:
        motivo = ""
        if e.estado not in ENTREGABLES:
            motivo = f"está en «{e.estado}»; la entrega es de unidades con descripción validada"
        else:
            regs = db.query(Archivo).filter(Archivo.codigo_carpeta == e.codigo_carpeta).all()
            if not regs or not any(r.ruta and Path(r.ruta).exists() for r in regs):
                motivo = "no tiene imágenes en el almacén"
            else:
                faltantes = division.faltantes([r.fragmento for r in regs])
                if not all(r.definitiva for r in regs):
                    motivo = ("las imágenes son de trabajo (cámara); falta cargar las del escáner "
                              "marcadas como definitivas")
                elif faltantes:
                    motivo = f"tomo incompleto, faltan las partes {', '.join(map(str, faltantes))}"
                elif not es_publicable(db, e):
                    motivo = "no cumple las condiciones de publicación: " + "; ".join(
                        motivos_de_bloqueo(db, e)[:2])
        (excluidas if motivo else incluibles).append(
            {"codigo": e.codigo_carpeta, "motivo": motivo} if motivo else e)
    return incluibles, excluidas


@router.post("/previa", summary="Qué entraría en el paquete de entrega y qué no")
def previa(s: Seleccion, db: Session = Depends(obtener_sesion),
           quien: Usuario = Depends(usuario_actual)) -> dict:
    _solo_administradora(quien)
    inc, exc = _seleccionar(db, s)
    return {"incluidas": [e.codigo_carpeta for e in inc], "excluidas": exc,
            "maximo_por_entrega": MAXIMO,
            "aviso": (f"Son más de {MAXIMO}; genere la entrega por periodo o por caja en varias "
                      "tandas." if len(inc) > MAXIMO else "")}


@router.post("/paquete", summary="Generar el paquete de entrega (zip)")
def paquete(s: Seleccion, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)):
    _solo_administradora(quien)
    inc, exc = _seleccionar(db, s)
    if not inc:
        raise HTTPException(409, "Ningún expediente de la selección está listo para entrega. "
                                 + "; ".join(f"{x['codigo']}: {x['motivo']}" for x in exc[:5]))
    if len(inc) > MAXIMO:
        raise HTTPException(413, f"La selección trae {len(inc)} expedientes y el máximo por entrega "
                                 f"es {MAXIMO}. Genérela por periodo o por caja.")
    destino = SALIDA / f"ENTREGA_{datetime.now():%Y%m%d_%H%M%S}.zip"
    try:
        r = paquete_entrega.construir(db, inc, quien.nombre, destino, s.incluir_maestra,
                                      os.getenv("CONTRATO_TEXTO", "Contrato 733 de 2026"))
    except HTTPException:
        destino.unlink(missing_ok=True)
        raise
    return FileResponse(r["archivo"], media_type="application/zip",
                        filename=Path(r["archivo"]).name,
                        headers={"X-Expedientes-Incluidos": str(len(inc)),
                                 "X-Expedientes-Excluidos": str(len(exc)),
                                 "X-Maestra-No-Conforme": str(r["maestra_no_conforme"])})
