"""
Propuesta de caja definitiva para el inventario de salida (F-GDM-003).

El sistema CALCULA una caja posible para cada carpeta, pero no la asigna: la propuesta no se
guarda en el expediente ni aparece en lo que ve el Servicio Geológico. Solo cuando la
administradora la confirma se crea la asignación real (caja definitiva y número de carpeta).

Reglas
  · Una caja es de un solo periodo: nunca se mezclan en una propuesta.
  · Dentro del periodo: serie y subserie en el orden de la tabla de valoración y, dentro de cada subserie, cronológico. Una caja no mezcla subseries.
  · Se llena por espesor, no por folios: hasta el límite que se indique (10 cm por defecto) de los 10,2 cm útiles de la X-100.
  · La administradora decide si cabe o no: puede cambiar el límite o pedir una carpeta por caja.
    Espesor estimado = folios × 0,1 mm + 0,3 cm de carpeta, o 1,5 cm de pastas si es libro.
  · Las cajas abiertas del mismo periodo se completan antes de abrir una nueva.
  · Lo que no cabe en una X-100 (más de 10 cm) va solo y queda señalado para decisión.
  · Los números de caja nuevos continúan después del mayor AH-CJ existente.
"""
from __future__ import annotations

import re
from datetime import date

LLENADO_CM = 10.0
CM_POR_FOLIO = 0.01
CM_CARPETA = 0.3
CM_PASTAS_LIBRO = 1.5


def espesor_cm(folios: int | None, es_libro: bool | None) -> float:
    return round((folios or 0) * CM_POR_FOLIO + (CM_PASTAS_LIBRO if es_libro else CM_CARPETA), 2)


def _numero(codigo: str) -> int:
    m = re.search(r"(\d+)\s*$", codigo or "")
    return int(m.group(1)) if m else 0


def _misma_subserie(db, caja: str, subserie_id: int) -> bool:
    """Una caja abierta solo se completa con carpetas de la misma subserie que ya trae."""
    from geology.modelos import Expediente
    ids = {i for (i,) in db.query(Expediente.subserie_id).filter(Expediente.caja_definitiva == caja).all()}
    return not ids or ids == {subserie_id}


def proponer(db, limite_cm: float | None = None, una_por_caja: bool = False,
             periodo: str | None = None) -> dict:
    from geology.modelos import Caja, Expediente, Periodo, Seccion, Serie, Subserie
    from geology.dominio.estados import Estado

    limite = float(limite_cm) if limite_cm else LLENADO_CM
    elegibles = (db.query(Expediente)
                   .filter(Expediente.estado.in_([Estado.ARCHIVADO.value,
                                                  Estado.DESCRIPCION_VALIDADA.value])).all())
    periodos = {p.id: p for p in db.query(Periodo).all()}
    subs = {s.id: s for s in db.query(Subserie).all()}
    series = {s.id: s for s in db.query(Serie).all()}
    secciones = {s.id: s for s in db.query(Seccion).all()}

    # Lo que ya ocupa cada caja abierta
    ocupado: dict[str, float] = {}
    periodo_caja: dict[str, str] = {}
    for e in db.query(Expediente).filter(Expediente.caja_definitiva.isnot(None),
                                          Expediente.caja_definitiva != "").all():
        ocupado[e.caja_definitiva] = ocupado.get(e.caja_definitiva, 0) + espesor_cm(e.volumen_folios, e.encuadernada)
    abiertas: dict[str, list[str]] = {}
    mayor = max([_numero(e.caja_definitiva) for e in
                 db.query(Expediente).filter(Expediente.caja_definitiva.isnot(None)).all()] +
                [_numero(c.codigo) for c in db.query(Caja).all()] + [0])
    for c in db.query(Caja).all():
        periodo_caja[c.codigo] = c.periodo
        if not c.cerrada:
            abiertas.setdefault(c.periodo, []).append(c.codigo)

    filas = []
    for e in elegibles:
        p = periodos.get(e.periodo_id)
        sub = subs.get(e.subserie_id)
        ser = series.get(sub.serie_id) if sub else None
        sec = secciones.get(ser.seccion_id) if ser else None
        filas.append({"exp": e, "periodo": p.numero_romano if p else "",
                      "orden_p": p.orden if p else 999,
                      "clave": (sec.codigo_dependencia if sec else "", ser.codigo if ser else "",
                                sub.codigo if sub else "", e.subserie_id or 0),
                      "serie": ser.nombre if ser else "", "subserie": sub.nombre if sub else "",
                      "esp": espesor_cm(e.volumen_folios, e.encuadernada)})
    # Periodo, luego serie y subserie en el orden de la tabla de valoración, y dentro de cada
    # subserie cronológico. Una caja no mezcla subseries: se abre otra en cada cambio.
    if periodo:
        filas = [f for f in filas if f["periodo"] == periodo.upper()]
    filas.sort(key=lambda f: (f["orden_p"], f["clave"], f["exp"].fecha_inicial or date.max,
                              f["exp"].fecha_final or date.max, f["exp"].codigo_carpeta))

    cajas: list[dict] = []
    sin_periodo: list[dict] = []
    actual: dict | None = None
    for f in filas:
        e = f["exp"]
        if not f["periodo"]:
            sin_periodo.append({"carpeta": e.codigo_carpeta,
                                "motivo": "Sin periodo: asígnelo en su ficha antes de proponer caja."})
            continue
        if (actual is None or actual["periodo"] != f["periodo"] or actual["cerrada_a_nuevas"]
                or actual["clave"] != f["clave"] or una_por_caja):
            actual = None
        # completar una caja abierta del mismo periodo, si cabe
        destino = None
        if actual and actual["espesor"] + f["esp"] <= limite:
            destino = actual
        if destino is None:
            for cod in ([] if una_por_caja else abiertas.get(f["periodo"], [])):
                ya = next((c for c in cajas if c["caja"] == cod), None)
                usado = ya["espesor"] if ya else ocupado.get(cod, 0)
                if usado + f["esp"] <= limite and _misma_subserie(db, cod, f["clave"][3]):
                    if ya is None:
                        ya = {"caja": cod, "periodo": f["periodo"], "existente": True, "clave": f["clave"],
                              "espesor": usado, "carpetas": [], "cerrada_a_nuevas": False, "avisos": []}
                        cajas.append(ya)
                    destino = ya
                    break
        if destino is None:
            mayor += 1
            destino = {"caja": f"AH-CJ-{mayor:05d}", "periodo": f["periodo"], "existente": False, "clave": f["clave"],
                       "espesor": 0.0, "carpetas": [], "cerrada_a_nuevas": False, "avisos": []}
            cajas.append(destino)
        destino["carpetas"].append({
            "carpeta": e.codigo_carpeta, "serie": f["serie"], "subserie": f["subserie"],
            "folios": e.volumen_folios or 0, "espesor_cm": f["esp"],
            "fechas": e.fechas_texto or "S/F", "titulo": e.titulo or e.nombre_expediente or "",
            "caja_origen": e.caja_origen or "", "libro": bool(e.encuadernada),
            "confirmable": e.estado == Estado.ARCHIVADO.value,
            "estado": e.estado})
        destino["espesor"] = round(destino["espesor"] + f["esp"], 2)
        if f["esp"] > limite:
            destino["avisos"].append(f"{e.codigo_carpeta} mide cerca de {f['esp']} cm y no cabe en la "
                                     "X-100: requiere definición (caja especial u otra solución).")
            destino["cerrada_a_nuevas"] = True
        actual = destino

    for c in cajas:
        c.pop("cerrada_a_nuevas", None)
        c["serie"], c["subserie"] = (c["carpetas"][0]["serie"], c["carpetas"][0]["subserie"])
        c.pop("clave", None)
        c["total"] = len(c["carpetas"])
        c["series"] = sorted({x["serie"] for x in c["carpetas"] if x["serie"]})
        if len(c["series"]) > 1:
            c["avisos"].append("Mezcla de series: " + "; ".join(c["series"]) + ".")
        sin_aprobar = [x["carpeta"] for x in c["carpetas"] if not x["confirmable"]]
        if sin_aprobar:
            c["avisos"].append(f"{len(sin_aprobar)} carpeta(s) aún sin descripción aprobada "
                               "(no se pueden confirmar todavía).")
        c["confirmable"] = any(x["confirmable"] for x in c["carpetas"])
        # Las terminadas que van seguidas desde el comienzo de la caja, sin una pendiente en medio
        seguidas = 0
        for x in c["carpetas"]:
            if not x["confirmable"]:
                break
            seguidas += 1
        c["terminadas"] = sum(1 for x in c["carpetas"] if x["confirmable"])
        c["terminadas_seguidas"] = seguidas
        pendientes = [x["carpeta"] for x in c["carpetas"] if not x["confirmable"]]
        c["mensaje"] = (
            f"Ya tiene {c['terminadas']} carpeta(s) terminada(s) que caben en {c['caja']}" +
            (f". Faltan por terminar, y van entre las fechas de esta caja: {', '.join(pendientes)}."
             if pendientes else ". Todas las de esta caja están terminadas.") if c["terminadas"] else
            f"Todavía no hay carpetas terminadas para {c['caja']}.")
    return {"cajas": cajas, "sin_periodo": sin_periodo,
            "llenado_cm": limite, "una_por_caja": una_por_caja,
            "nota": ("Es una propuesta: no cambia nada hasta que la administradora la confirme. "
                     "El espesor es una estimación (folios × 0,1 mm + carpeta o pastas).")}
