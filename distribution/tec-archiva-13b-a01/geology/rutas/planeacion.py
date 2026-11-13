"""
Planeación por periodos: del inventario de origen a la entrega completa.

Responde cuatro preguntas del equipo: qué carpetas tiene cada caja, a qué periodo pertenece
cada carpeta según sus fechas, cuánto falta para cerrar cada periodo y qué sigue para no saltar
de periodo.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from geology.dominio import planeacion as pl
from geology.dominio.estados import Usuario
from geology.nucleo.bd import obtener_sesion
from geology.rutas.cuentas import usuario_actual

router = APIRouter(prefix="/planeacion", tags=["Planeación por periodos"])

BANDERAS = {
    "cruza_periodos": "Las fechas cruzan periodos",
    "sin_fecha": "Sin fecha: el periodo sale del inventario y falta confirmarlo",
    "fecha_fuera_de_periodos": "La fecha no cae en ningún periodo",
    "difiere_del_inventario": "El inventario de origen dice otro periodo",
    "sin_periodo": "Sin periodo: lo asigna una persona",
}


def _acceso(quien: Usuario) -> None:
    if quien.es_entidad:
        raise HTTPException(403, "La planeación es del equipo del proyecto.")


@router.get("/resumen", summary="Cuánto falta para cerrar cada periodo")
def resumen(refrescar: bool = Query(False), db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    _acceso(quien)
    plan = pl.construir(db, refrescar)
    return {
        "en_curso": plan["en_curso"],
        "periodos": plan["resumen"],
        "sin_periodo": len(plan["sin_periodo"]),
        "cajas_mixtas": {k: v for k, v in plan["mixtas"].items()},
        "total_carpetas": len(plan["carpetas"]),
        "total_cajas": len(plan["cajas"]),
        "banderas": BANDERAS,
        "mensaje": ("Todos los periodos con carpetas están completos." if not plan["en_curso"] else
                    f"Periodo en curso: {plan['en_curso']}. No pase al siguiente hasta cerrarlo."),
    }


@router.get("/siguiente", summary="Qué sigue, sin saltar de periodo")
def siguiente(limite: int = Query(60, le=500), db: Session = Depends(obtener_sesion),
              quien: Usuario = Depends(usuario_actual)) -> dict:
    _acceso(quien)
    return pl.siguiente(pl.construir(db), limite)


@router.get("/periodo/{romano}", summary="Las cajas y carpetas de un periodo")
def del_periodo(romano: str, solo_pendientes: bool = Query(False),
                db: Session = Depends(obtener_sesion),
                quien: Usuario = Depends(usuario_actual)) -> dict:
    _acceso(quien)
    plan = pl.construir(db)
    romano = romano.upper()
    if romano == "SIN":
        del_p = plan["sin_periodo"]
    else:
        del_p = [c for c in plan["carpetas"] if c.periodo == romano]
    if solo_pendientes:
        del_p = [c for c in del_p if c.etapa not in ("en_inventario",)]
    cajas: dict[str, list] = {}
    for c in del_p:
        cajas.setdefault(c.caja_origen or "(sin caja)", []).append(c)
    return {"periodo": romano, "total": len(del_p),
            "cajas": [{"caja": k, "carpetas": [x.como_dict() for x in v],
                       "periodos_de_la_caja": plan["mixtas"].get(k, [romano]),
                       "mixta": k in plan["mixtas"]}
                      for k, v in sorted(cajas.items())]}


@router.get("/cajas", summary="Las cajas del FUID de origen con sus carpetas")
def cajas(buscar: str = Query("", description="Caja o carpeta"), limite: int = Query(200, le=2000),
          db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    """Para cada caja de origen, las carpetas que trae el inventario y el periodo de cada una."""
    _acceso(quien)
    plan = pl.construir(db)
    t = buscar.strip().upper()
    salida = []
    for caja, lista in sorted(plan["cajas"].items()):
        if t and t not in caja.upper() and not any(t in c.codigo for c in lista):
            continue
        periodos = sorted({c.periodo for c in lista if c.periodo})
        salida.append({"caja": caja, "carpetas": [c.como_dict() for c in lista],
                       "total": len(lista), "periodos": periodos, "mixta": len(periodos) > 1})
        if len(salida) >= limite:
            break
    return {"cajas": salida, "total_cajas": len(plan["cajas"])}


@router.get("/excel", summary="El plan completo en Excel")
def excel(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    _acceso(quien)
    plan = pl.construir(db, True)
    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Carpetas por periodo"
    enc = ["Periodo (por fechas)", "Caja de origen", "Carpeta", "Fecha inicial", "Fecha final", "Folios",
           "Periodo según inventario", "Origen del periodo", "Etapa", "Qué sigue", "Observaciones"]
    ws.append(enc)
    orden = plan["orden"]
    for c in sorted(plan["carpetas"], key=lambda x: (orden.get(x.periodo, 999), x.caja_origen, x.codigo)):
        d = c.como_dict()
        ws.append([c.periodo or "SIN PERIODO", c.caja_origen, c.codigo, d["fecha_inicial"],
                   d["fecha_final"], c.folios, c.periodo_inventario, c.origen, d["etapa_rotulo"],
                   d["accion"], "; ".join(BANDERAS.get(b, b) for b in c.banderas)])
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="5A3D22")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col, ancho in zip("ABCDEFGHIJK", (14, 16, 16, 12, 12, 8, 16, 16, 26, 28, 60)):
        ws.column_dimensions[col].width = ancho

    r2 = libro.create_sheet("Cierre por periodo")
    r2.append(["Periodo", "Rango", "Carpetas", "Folios", "Cajas", "Terminadas", "Pendientes",
               "% terminado", "¿Completo?", "Cajas que mezclan periodos"])
    for r in plan["resumen"]:
        r2.append([r["periodo"], r["rango"], r["carpetas"], r["folios"], r["cajas"], r["terminadas"],
                   r["pendientes"], r["porcentaje"], "Sí" if r["completo"] else "No",
                   ", ".join(r["cajas_mixtas"])])
    for celda in r2[1]:
        celda.font = Font(bold=True)
    salida = io.BytesIO()
    libro.save(salida)
    return Response(salida.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Planeacion_por_periodos.xlsx"'})
