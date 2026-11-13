"""
¿Alcanzan las llaves para terminar todas las cajas antes del cierre del contrato?

Es una estimación, no una promesa, y la pantalla lo dice. Se cuentan las carpetas del
inventario que todavía no llegaron a «Hoja de control por revisar», se calcula cuántas
peticiones a los modelos cuesta cada una (una por cada bloque de páginas que se lee, más una
de revisión) y se compara con lo que las llaves pueden dar por día según los topes que la
administradora tiene configurados, entre ahora y la fecha de cierre.

Las llaves gratuitas van primero y la paga queda de reserva, así que el resultado dice
cuánto del trabajo cubren las gratuitas y cuánto tendría que cubrir la paga.
"""
from __future__ import annotations

import math
import os
from datetime import date

from sqlalchemy.orm import Session

from geology.dominio import lectores
from geology.dominio import seguimiento as seg
from geology.dominio.estados import Estado


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, str(defecto)))
    except ValueError:
        return defecto


def estimar(db: Session) -> dict:
    from geology.modelos import Expediente, UnidadInventario

    meta_cajas = _entero("META_CAJAS", 1020)
    try:
        fin = date.fromisoformat(os.getenv("FECHA_FIN_CONTRATO", "2026-12-31"))
    except ValueError:
        fin = date(2026, 12, 31)
    bloque = max(1, _entero("TOPE_PAGINAS_RIGOR", 60))
    umbral = max(1, _entero("PAGINAS_RIGOR", 60))
    extra = max(0, _entero("PETICIONES_EXTRA_POR_CARPETA", 1))   # la revisión
    hecha = seg.ETAPA_HECHA["hoja_control"]

    cajas, total, pendientes, folios_pend, peticiones = set(), 0, 0, 0, 0
    q = (db.query(UnidadInventario.caja_origen, UnidadInventario.folios, Expediente.estado)
           .outerjoin(Expediente, Expediente.codigo_carpeta == UnidadInventario.codigo_carpeta))
    for caja, folios, estado in q.yield_per(1000):
        total += 1
        if caja:
            cajas.add(caja)
        if estado == Estado.RETIRADO.value or seg.RANGO.get(estado, -1) >= hecha:
            continue
        pendientes += 1
        f = folios or 0
        folios_pend += f
        lectura = math.ceil(f / bloque) if f > umbral else 1
        peticiones += lectura + extra

    gratis = paga = 0
    for m in lectores.motores():
        if m["paga"]:
            paga += m["cuota_diaria"]
        else:
            gratis += m["cuota_diaria"]

    hoy = date.today()
    dias = seg.dias_habiles(hoy, fin)
    necesarias = math.ceil(peticiones / dias) if dias else peticiones
    total_dia = gratis + paga

    if not peticiones:
        veredicto, nivel = "No hay carpetas pendientes de hoja de control.", "verde"
    elif not total_dia:
        veredicto, nivel = "No hay llaves configuradas.", "rojo"
    elif gratis >= necesarias:
        veredicto, nivel = ("Las llaves gratuitas solas alcanzan. La paga queda de reserva por si "
                            "alguna se agota."), "verde"
    elif total_dia >= necesarias:
        veredicto, nivel = (f"Las gratuitas no alcanzan solas: la paga tendría que aportar unas "
                            f"{necesarias - gratis:,} peticiones por día."), "amarillo"
    else:
        veredicto, nivel = (f"No alcanza con los topes actuales: faltan unas {necesarias - total_dia:,} "
                            "peticiones por día. Suba el tope de la paga o agregue llaves."), "rojo"

    return {
        "meta_cajas": meta_cajas, "metros_lineales": round(meta_cajas / 4, 1),
        "cajas_cargadas": len(cajas), "carpetas": total, "carpetas_pendientes": pendientes,
        "folios_pendientes": folios_pend, "peticiones_estimadas": peticiones,
        "fecha_cierre": fin.isoformat(), "dias_habiles_restantes": dias,
        "peticiones_por_dia_necesarias": necesarias,
        "capacidad_gratuitas_por_dia": gratis, "capacidad_paga_por_dia": paga,
        "veredicto": veredicto, "nivel": nivel,
        "aviso": ("Estimación según los topes configurados, que pueden ser mayores que el límite "
                  "real de Google. Los festivos no se descuentan. Si en la base hay menos cajas "
                  "que la meta, el cálculo solo cubre las cargadas."),
    }
