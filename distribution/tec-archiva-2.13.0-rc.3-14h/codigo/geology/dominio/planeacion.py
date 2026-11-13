"""
Planeación de la entrega por periodos.

La regla del contrato es que todas las carpetas de un periodo se entregan juntas, no por goteo.
Para garantizarlo hay que saber, con el inventario de origen a la vista, qué carpetas tiene cada
caja, a qué periodo pertenece cada una según sus FECHAS (no según la casilla del inventario,
que se levantó hace años con la información de entonces), qué cajas mezclan periodos y qué
falta para cerrar cada periodo antes de pasar al siguiente.

Nada de aquí escribe en la base de datos: es una lectura del inventario de origen cruzada con
el estado real de cada expediente.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

from geology.dominio.estados import Estado
from geology.dominio.periodos import RangoPeriodo, resolver_por_fechas

# Etapas de una carpeta, de menos a más avanzada. La clave es la que usa la pantalla.
ETAPAS = ("sin_cargar", "en_hoja", "hoja_revisada", "descrita", "validada", "en_inventario")
ETAPA_ROTULO = {"sin_cargar": "Sin cargar", "en_hoja": "Hoja de control en trabajo",
                "hoja_revisada": "Hoja revisada", "descrita": "Descripción por validar",
                "validada": "Descripción validada", "en_inventario": "En inventario de salida",
                "retirada": "Retirada del flujo"}
_POR_ESTADO = {
    Estado.EN_COLA.value: "en_hoja", Estado.EN_PROCESAMIENTO.value: "en_hoja",
    Estado.HOJA_EN_ELABORACION.value: "en_hoja", Estado.HOJA_POR_REVISAR.value: "en_hoja",
    Estado.DEVUELTO.value: "en_hoja",
    Estado.HOJA_REVISADA.value: "hoja_revisada",
    Estado.DESCRIPCION_POR_VALIDAR.value: "descrita",
    Estado.DESCRIPCION_VALIDADA.value: "validada", Estado.ARCHIVADO.value: "validada",
    Estado.EN_INVENTARIO.value: "en_inventario",
    Estado.RETIRADO.value: "retirada",
}
ACCION = {"sin_cargar": "Subir el PDF en Cargue", "en_hoja": "Terminar y revisar la hoja",
          "hoja_revisada": "Escribir el ISAD(G)", "descrita": "Validar la ficha",
          "validada": "Asignar caja definitiva", "en_inventario": "Terminada",
          "retirada": "Retirada"}


@dataclass
class Carpeta:
    codigo: str
    caja_origen: str
    folios: int | None
    fecha_inicial: date | None
    fecha_final: date | None
    periodo_inventario: str
    periodo: str                # el que resulta de las fechas (o de lo fijado a mano)
    origen: str                 # fechas | manual | inventario | sin dato
    etapa: str
    estado: str
    banderas: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"carpeta": self.codigo, "caja_origen": self.caja_origen, "folios": self.folios,
                "fecha_inicial": self.fecha_inicial.isoformat() if self.fecha_inicial else "",
                "fecha_final": self.fecha_final.isoformat() if self.fecha_final else "",
                "periodo_inventario": self.periodo_inventario, "periodo": self.periodo,
                "origen_periodo": self.origen, "etapa": self.etapa,
                "etapa_rotulo": ETAPA_ROTULO.get(self.etapa, self.etapa), "estado": self.estado,
                "banderas": self.banderas, "accion": ACCION.get(self.etapa, "")}


_cache: dict = {"t": 0.0, "v": None}


def construir(db, refrescar: bool = False) -> dict:
    """El plan completo. Se guarda 20 segundos para no recalcularlo en cada clic."""
    if not refrescar and _cache["v"] is not None and time.time() - _cache["t"] < 20:
        return _cache["v"]
    from geology.modelos import Expediente, Periodo, UnidadInventario

    periodos = db.query(Periodo).order_by(Periodo.orden).all()
    orden = {p.numero_romano: i for i, p in enumerate(periodos)}
    rangos = [RangoPeriodo(p.numero_romano, p.fecha_inicio, p.fecha_fin) for p in periodos]
    por_id = {p.id: p.numero_romano for p in periodos}

    exps = {e.codigo_carpeta: e for e in db.query(Expediente).all()}
    carpetas: list[Carpeta] = []
    for u in db.query(UnidadInventario).order_by(UnidadInventario.codigo_carpeta).all():
        e = exps.get(u.codigo_carpeta)
        fi = (e.fecha_inicial if e and e.fecha_inicial else u.fecha_inicial)
        ff = (e.fecha_final if e and e.fecha_final else u.fecha_final)
        inv = (u.periodo or "").strip().upper()
        inv = "" if inv in ("", "S/F", "SF", "SIN FECHA", "N/A", "SP") else inv
        banderas: list[str] = []

        if e and e.periodo_fijado_a_mano and e.periodo_id in por_id:
            periodo, origen = por_id[e.periodo_id], "manual"
        else:
            r = resolver_por_fechas(fi, ff, rangos)
            if r.resuelto:
                periodo, origen = r.romano, "fechas"
                if "cruzan" in (r.aviso or ""):
                    banderas.append("cruza_periodos")
            elif not (fi or ff):
                periodo, origen = (inv, "inventario") if inv else ("", "sin dato")
                banderas.append("sin_fecha")
            else:
                periodo, origen = "", "sin dato"
                banderas.append("fecha_fuera_de_periodos")
        if inv and periodo and inv != periodo and origen != "inventario":
            banderas.append("difiere_del_inventario")
        if not periodo:
            banderas.append("sin_periodo")

        etapa = _POR_ESTADO.get(e.estado, "en_hoja") if e else "sin_cargar"
        carpetas.append(Carpeta(u.codigo_carpeta, u.caja_origen or "", u.folios, fi, ff, inv,
                                periodo, origen, etapa, e.estado if e else "", banderas))

    # Cajas y sus periodos
    cajas: dict[str, list[Carpeta]] = {}
    for c in carpetas:
        cajas.setdefault(c.caja_origen or "(sin caja)", []).append(c)
    mixtas = {k: sorted({c.periodo for c in v if c.periodo}) for k, v in cajas.items()
              if len({c.periodo for c in v if c.periodo}) > 1}

    resumen = []
    for p in periodos:
        del_p = [c for c in carpetas if c.periodo == p.numero_romano]
        cont = {k: 0 for k in (*ETAPAS, "retirada")}
        for c in del_p:
            cont[c.etapa] += 1
        activas = [c for c in del_p if c.etapa != "retirada"]
        terminadas = cont["en_inventario"]
        resumen.append({
            "periodo": p.numero_romano, "rango": p.rango_texto,
            "inicio": p.fecha_inicio.isoformat() if p.fecha_inicio else "",
            "fin": p.fecha_fin.isoformat() if p.fecha_fin else "",
            "carpetas": len(del_p), "folios": sum(c.folios or 0 for c in del_p),
            "cajas": len({c.caja_origen for c in del_p}),
            "etapas": cont, "terminadas": terminadas,
            "pendientes": len(activas) - terminadas,
            "porcentaje": round(100 * terminadas / len(activas), 1) if activas else 0,
            "completo": bool(activas) and terminadas == len(activas),
            "cajas_mixtas": sorted(k for k, ps in mixtas.items() if p.numero_romano in ps),
            "con_banderas": sum(1 for c in del_p if c.banderas),
        })

    sin = [c for c in carpetas if not c.periodo]
    en_curso = next((r["periodo"] for r in resumen if r["carpetas"] and not r["completo"]), None)
    plan = {"carpetas": carpetas, "cajas": cajas, "mixtas": mixtas, "resumen": resumen,
            "sin_periodo": sin, "en_curso": en_curso, "orden": orden}
    _cache["t"], _cache["v"] = time.time(), plan
    return plan


def siguiente(plan: dict, limite: int = 60) -> dict:
    """
    Qué sigue. Se trabaja periodo por periodo, en el orden cronológico de las tablas de
    valoración, y dentro del periodo caja por caja. Lo que pertenece a un periodo posterior al
    que está en curso queda fuera de la lista: es justo el salto que hay que evitar.
    """
    en_curso = plan["en_curso"]
    if not en_curso:
        return {"en_curso": None, "items": [], "mensaje": "No hay periodos con carpetas pendientes."}
    cola = [c for c in plan["carpetas"]
            if c.periodo == en_curso and c.etapa not in ("en_inventario", "retirada")]
    # Primero lo más atrasado: así cada caja se cierra completa en vez de quedar a medias.
    cola.sort(key=lambda c: (ETAPAS.index(c.etapa) if c.etapa in ETAPAS else 0,
                             c.caja_origen, c.codigo))
    return {"en_curso": en_curso, "pendientes": len(cola),
            "items": [c.como_dict() for c in cola[:limite]],
            "mensaje": (f"Periodo en curso: {en_curso}. Quedan {len(cola)} carpeta(s) para "
                        "cerrarlo antes de pasar al siguiente.")}


def aviso_de_salto(plan: dict, codigo_carpeta: str) -> str:
    """Para el cargue: avisa si la carpeta es de un periodo posterior al que está en curso."""
    en_curso = plan["en_curso"]
    c = next((x for x in plan["carpetas"] if x.codigo == codigo_carpeta), None)
    if not c or not en_curso or not c.periodo:
        return ""
    if plan["orden"].get(c.periodo, 0) > plan["orden"].get(en_curso, 0):
        return (f"Esta carpeta es del periodo {c.periodo}, pero el periodo en curso es el "
                f"{en_curso} y aún no está completo. Se puede cargar, pero la entrega exige "
                "cerrar cada periodo completo antes de pasar al siguiente.")
    return ""
