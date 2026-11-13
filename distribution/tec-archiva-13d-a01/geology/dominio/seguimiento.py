"""
Seguimiento del contrato: a quién se le asignó qué, cómo va cada persona y si se cumple el
cronograma.

Regla de diseño: aquí no se guarda avance. Cada asignación apunta a una carpeta, y si esa
carpeta ya llegó al estado que cierra la etapa, está hecha; si no, está pendiente, en curso,
devuelta, vencida o colgada según lo que diga la bitácora. Un contador aparte se desincroniza
y la bitácora no.

Los días hábiles son de lunes a viernes. Los festivos no se descuentan: si un festivo cae en
medio de una meta, el plan sale un día más exigente de lo real, y eso se dice en pantalla.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func

from geology.dominio.estados import Estado
from geology.dominio.produccion import LABORES, _embudo

ETAPAS = {"hoja_control": "Hoja de control", "descripcion": "Descripción"}

# Qué tan avanzado está un expediente. Devuelto y retirado se tratan aparte.
RANGO = {
    Estado.EN_COLA.value: 0, Estado.EN_PROCESAMIENTO.value: 1,
    Estado.HOJA_EN_ELABORACION.value: 2, Estado.HOJA_POR_REVISAR.value: 3,
    Estado.HOJA_REVISADA.value: 4, Estado.DESCRIPCION_POR_VALIDAR.value: 5,
    Estado.DESCRIPCION_VALIDADA.value: 6, Estado.ARCHIVADO.value: 7,
    Estado.EN_INVENTARIO.value: 8,
}
# Rango desde el cual la etapa asignada está terminada por quien la trabaja.
ETAPA_HECHA = {"hoja_control": 3, "descripcion": 5}

DIAS_COLGADA = 3          # una carpeta abierta sin ningún movimiento en 3 días está colgada
DIAS_SIN_ACTIVIDAD = 2    # una persona con carpetas abiertas y sin actividad en 2 días hábiles
DIAS_DE_ACTIVIDAD = 14


def hoy() -> date:
    return date.today()


def dias_habiles(desde: date, hasta: date) -> int:
    """Lunes a viernes entre dos fechas, ambas incluidas."""
    if hasta < desde:
        return 0
    n, d = 0, desde
    while d <= hasta:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


# ---------------------------------------------------------------------------------------
# Asignaciones
# ---------------------------------------------------------------------------------------
def _personas(db) -> dict:
    """Las cuentas activas del equipo, con las dos formas en que la bitácora las nombra."""
    from geology.modelos import UsuarioBD
    filas = (db.query(UsuarioBD).filter(UsuarioBD.activo.is_(True))
               .filter(UsuarioBD.rol.in_(("equipo", "lider", "administradora"))).all())
    return {u.correo: u for u in filas}


def _ultimos_movimientos(db, ids_exp: list[int]) -> tuple[dict, dict]:
    """Último movimiento de cada expediente, y el último de cada persona sobre cada uno."""
    from geology.modelos import Trazabilidad
    if not ids_exp:
        return {}, {}
    ult, por_persona = {}, {}
    for i in range(0, len(ids_exp), 5000):
        trozo = ids_exp[i:i + 5000]
        for eid, usuario, f in (db.query(Trazabilidad.expediente_id, Trazabilidad.usuario,
                                         func.max(Trazabilidad.fecha))
                                  .filter(Trazabilidad.expediente_id.in_(trozo))
                                  .group_by(Trazabilidad.expediente_id, Trazabilidad.usuario).all()):
            if f and (eid not in ult or f > ult[eid]):
                ult[eid] = f
            por_persona[(eid, usuario)] = f
    return ult, por_persona


def estado_de_asignacion(a, exp, ult_mov, mov_persona, nombres: set, ahora: datetime) -> dict:
    """El estado vivo de una asignación. `nombres` son las formas de nombrar a la persona."""
    d = {"id": a.id, "carpeta": a.codigo_carpeta, "persona": a.persona, "etapa": a.etapa,
         "etapa_texto": ETAPAS.get(a.etapa, a.etapa),
         "asignado_en": a.asignado_en.isoformat(timespec="minutes") if a.asignado_en else None,
         "fecha_limite": a.fecha_limite.isoformat() if a.fecha_limite else None,
         "nota": a.nota, "estado_expediente": exp.estado if exp else "Sin documento cargado"}
    hecha_en = ETAPA_HECHA.get(a.etapa, 3)
    rango = RANGO.get(exp.estado, -1) if exp else -1
    suyo = max((mov_persona.get((exp.id, n)) for n in nombres if mov_persona.get((exp.id, n))),
               default=None) if exp else None
    if exp is not None and exp.estado == Estado.RETIRADO.value:
        estado = "retirada"
    elif rango >= hecha_en:
        estado = "hecha"
    elif exp is not None and exp.estado == Estado.DEVUELTO.value:
        estado = "devuelta"
    elif exp is None:
        estado = "sin_documento"
    elif suyo and a.asignado_en and suyo >= a.asignado_en or rango >= 2:
        estado = "en_curso"
    else:
        estado = "pendiente"
    abierta = estado not in ("hecha", "retirada")
    ultimo = max([x for x in (ult_mov.get(exp.id) if exp else None, a.asignado_en) if x], default=None)
    sin_mover = (ahora - ultimo).days if ultimo else 0
    d.update({
        "estado": estado,
        "vencida": bool(abierta and a.fecha_limite and a.fecha_limite < ahora.date()),
        "colgada": bool(abierta and estado != "sin_documento" and sin_mover >= DIAS_COLGADA),
        "dias_sin_mover": sin_mover if abierta else 0,
        "ultimo_movimiento": ultimo.isoformat(timespec="minutes") if ultimo else None,
    })
    return d


def asignaciones_vivas(db, solo_persona: str | None = None, solo_abiertas: bool = False) -> list[dict]:
    """Las asignaciones activas con su estado real."""
    from geology.modelos import Asignacion, Expediente
    q = db.query(Asignacion).filter(Asignacion.activa.is_(True))
    if solo_persona:
        q = q.filter(Asignacion.persona == solo_persona)
    filas = q.order_by(Asignacion.asignado_en.desc(), Asignacion.id.desc()).all()
    if not filas:
        return []
    codigos = list({a.codigo_carpeta for a in filas})
    exps = {}
    for i in range(0, len(codigos), 5000):
        for e in db.query(Expediente).filter(Expediente.codigo_carpeta.in_(codigos[i:i + 5000])).all():
            exps[e.codigo_carpeta] = e
    ult, por_persona = _ultimos_movimientos(db, [e.id for e in exps.values()])
    personas = _personas(db)
    from geology.modelos import UsuarioBD
    todos = {u.correo: u for u in db.query(UsuarioBD).all()}
    ahora = datetime.now()
    salida = []
    for a in filas:
        u = todos.get(a.persona)
        nombres = {a.persona} | ({u.nombre} if u else set())
        d = estado_de_asignacion(a, exps.get(a.codigo_carpeta), ult, por_persona, nombres, ahora)
        d["persona_nombre"] = u.nombre if u else a.persona
        if solo_abiertas and d["estado"] in ("hecha", "retirada"):
            continue
        salida.append(d)
    return salida


# ---------------------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------------------
def actividad_por_persona(db, nombres_a_correo: dict, dias: int = DIAS_DE_ACTIVIDAD) -> dict:
    """Cuántas carpetas distintas movió cada persona cada día, y cuándo fue su último movimiento."""
    from geology.modelos import Trazabilidad
    desde = datetime.combine(hoy() - timedelta(days=dias - 1), datetime.min.time())
    filas = (db.query(func.date(Trazabilidad.fecha), Trazabilidad.usuario,
                      func.count(func.distinct(Trazabilidad.expediente_id)))
               .filter(Trazabilidad.fecha >= desde, Trazabilidad.usuario.isnot(None),
                       Trazabilidad.accion.in_(list(LABORES)))
               .group_by(func.date(Trazabilidad.fecha), Trazabilidad.usuario).all())
    dias_lista = [(hoy() - timedelta(days=dias - 1 - i)) for i in range(dias)]
    por = {}
    for d, usuario, n in filas:
        correo = nombres_a_correo.get(usuario)
        if not correo:
            continue
        dd = d if isinstance(d, date) else date.fromisoformat(str(d))
        por.setdefault(correo, {})[dd] = por.get(correo, {}).get(dd, 0) + n
    ultimas = dict(db.query(Trazabilidad.usuario, func.max(Trazabilidad.fecha))
                     .filter(Trazabilidad.usuario.isnot(None), Trazabilidad.accion.in_(list(LABORES)))
                     .group_by(Trazabilidad.usuario).all())
    ult_por_correo = {}
    for nombre, f in ultimas.items():
        c = nombres_a_correo.get(nombre)
        if c and f and (c not in ult_por_correo or f > ult_por_correo[c]):
            ult_por_correo[c] = f
    return {"dias": [d.isoformat() for d in dias_lista], "por_persona": por,
            "ultima": ult_por_correo, "lista_dias": dias_lista}


def tablero_personas(db, vivas: list[dict]) -> list[dict]:
    from geology.modelos import UsuarioBD
    cuentas = _personas(db)
    nombres_a_correo = {}
    for u in cuentas.values():
        nombres_a_correo[u.nombre] = u.correo
        nombres_a_correo[u.correo] = u.correo
    act = actividad_por_persona(db, nombres_a_correo)
    ahora = datetime.now()
    filas = []
    for correo, u in cuentas.items():
        mias = [v for v in vivas if v["persona"] == correo]
        abiertas = [v for v in mias if v["estado"] not in ("hecha", "retirada")]
        serie = [act["por_persona"].get(correo, {}).get(d, 0) for d in act["lista_dias"]]
        ultima = act["ultima"].get(correo)
        habiles_sin = (dias_habiles(ultima.date() + timedelta(days=1), hoy())
                       if ultima else None)
        desde_asignada = min((v["asignado_en"] for v in abiertas if v["asignado_en"]), default=None)
        recien = bool(desde_asignada and
                      (ahora - datetime.fromisoformat(desde_asignada)).days < DIAS_SIN_ACTIVIDAD)
        if not abiertas:
            semaforo, lectura = "gris", "Sin carpetas abiertas"
        elif ultima is None and recien:
            semaforo, lectura = "gris", "Recién asignada, aún sin movimientos"
        elif ultima is None:
            semaforo, lectura = "rojo", "Tiene carpetas y nunca ha registrado actividad"
        elif habiles_sin >= DIAS_SIN_ACTIVIDAD + 2:
            semaforo, lectura = "rojo", f"Sin actividad hace {habiles_sin} días hábiles"
        elif habiles_sin >= DIAS_SIN_ACTIVIDAD:
            semaforo, lectura = "amarillo", f"Sin actividad hace {habiles_sin} días hábiles"
        else:
            semaforo, lectura = "verde", "Trabajando"
        cuenta = lambda e: sum(1 for v in mias if v["estado"] == e)
        filas.append({
            "correo": correo, "nombre": u.nombre, "cargo": u.cargo, "rol": u.rol,
            "funcion": u.funcion, "sin_limites": bool(getattr(u, "sin_limites", False)),
            "asignadas": len(mias), "hechas": cuenta("hecha"), "en_curso": cuenta("en_curso"),
            "pendientes": cuenta("pendiente") + cuenta("sin_documento"),
            "devueltas": cuenta("devuelta"),
            "vencidas": sum(1 for v in mias if v["vencida"]),
            "colgadas": sum(1 for v in mias if v["colgada"]),
            "ultima_actividad": ultima.isoformat(timespec="minutes") if ultima else None,
            "dias_habiles_sin_actividad": habiles_sin,
            "actividad_14d": serie, "movidas_14d": sum(serie),
            "semaforo": semaforo, "lectura": lectura})
    filas.sort(key=lambda f: ({"rojo": 0, "amarillo": 1, "verde": 2, "gris": 3}[f["semaforo"]],
                              -f["vencidas"], -f["colgadas"], f["nombre"]))
    return filas, act["dias"]


# ---------------------------------------------------------------------------------------
# Cronograma
# ---------------------------------------------------------------------------------------
def _carpetas_del_hito(db, h) -> list[str]:
    from geology.modelos import UnidadInventario
    q = db.query(UnidadInventario.codigo_carpeta)
    if h.periodo:
        q = q.filter(UnidadInventario.periodo == h.periodo)
    return [c for (c,) in q.all()]


def avance_de_hito(db, h) -> dict:
    """Plan contra realidad de una meta, con ritmo requerido, ritmo actual y proyección."""
    from geology.modelos import Expediente, Trazabilidad
    rango_meta = RANGO.get(h.estado_meta, 6)
    codigos = _carpetas_del_hito(db, h)
    universo = len(codigos)
    meta = h.meta_carpetas or universo
    estados_ok = [e for e, r in RANGO.items() if r >= rango_meta]

    hechas_ids, real = [], 0
    for i in range(0, len(codigos), 5000):
        filas = (db.query(Expediente.id).filter(Expediente.codigo_carpeta.in_(codigos[i:i + 5000]),
                                                Expediente.estado.in_(estados_ok)).all())
        hechas_ids += [x for (x,) in filas]
    real = len(hechas_ids)

    # Curva real: el día en que cada carpeta llegó por primera vez al estado de la meta.
    por_dia = {}
    for i in range(0, len(hechas_ids), 5000):
        for f in (db.query(func.min(Trazabilidad.fecha))
                    .filter(Trazabilidad.expediente_id.in_(hechas_ids[i:i + 5000]),
                            Trazabilidad.estado_nuevo.in_(estados_ok))
                    .group_by(Trazabilidad.expediente_id).all()):
            d = f[0].date() if f[0] else None
            if d:
                por_dia[d] = por_dia.get(d, 0) + 1

    hoy_ = hoy()
    ini, fin = h.fecha_inicio, h.fecha_fin
    total_h = max(1, dias_habiles(ini, fin))
    pasados = min(total_h, dias_habiles(ini, min(hoy_, fin))) if hoy_ >= ini else 0
    esperado = round(meta * pasados / total_h)
    restantes_h = dias_habiles(max(hoy_ + timedelta(days=1), ini), fin) if hoy_ < fin else 0
    faltan = max(0, meta - real)
    requerido = round(faltan / restantes_h, 2) if restantes_h else (0 if not faltan else None)
    ult7 = sum(n for d, n in por_dia.items() if d > hoy_ - timedelta(days=7))
    habiles_7 = max(1, dias_habiles(hoy_ - timedelta(days=6), hoy_))
    ritmo = round(ult7 / habiles_7, 1)
    proyeccion = None
    if faltan == 0:
        proyeccion = "Meta cumplida"
    elif ritmo > 0:
        n, d = 0, hoy_
        need = faltan
        dias = 0
        while need > 0 and dias < 2000:
            d += timedelta(days=1)
            if d.weekday() < 5:
                need -= ritmo
            dias += 1
        proyeccion = d.isoformat()
    if faltan == 0:
        semaforo = "verde"
    elif hoy_ < ini:
        semaforo = "gris"
    elif real >= esperado * 0.95:
        semaforo = "verde"
    elif real >= esperado * 0.80:
        semaforo = "amarillo"
    else:
        semaforo = "rojo"
    if hoy_ > fin and faltan:
        semaforo = "rojo"

    # Series para la gráfica: plan lineal y real acumulado, día calendario a día calendario.
    serie, acum, d = [], 0, ini
    fin_graf = max(fin, min(hoy_, fin + timedelta(days=30)))
    anteriores = sum(n for dd, n in por_dia.items() if dd < ini)
    acum = anteriores
    habiles_vistos = 0
    while d <= fin_graf:
        if d.weekday() < 5 and d <= fin:
            habiles_vistos += 1
        acum += por_dia.get(d, 0)
        serie.append({"dia": d.isoformat(),
                      "plan": round(meta * min(habiles_vistos, total_h) / total_h, 1),
                      "real": acum if d <= hoy_ else None})
        d += timedelta(days=1)
    return {"id": h.id, "nombre": h.nombre, "periodo": h.periodo or "Todo el contrato",
            "fecha_inicio": ini.isoformat(), "fecha_fin": fin.isoformat(),
            "estado_meta": h.estado_meta, "universo": universo, "meta": meta, "real": real,
            "esperado_a_hoy": esperado, "faltan": faltan,
            "dias_habiles_restantes": restantes_h, "ritmo_requerido": requerido,
            "ritmo_actual_7d": ritmo, "proyeccion_fin": proyeccion, "semaforo": semaforo,
            "pct_real": round(100 * real / meta, 1) if meta else 0,
            "pct_esperado": round(100 * esperado / meta, 1) if meta else 0,
            "serie": serie}


def resumen(db) -> dict:
    from geology.modelos import HitoCronograma, UnidadInventario, Expediente
    vivas = asignaciones_vivas(db)
    personas, dias = tablero_personas(db, vivas)
    universo, embudo = _embudo(db)
    asignadas_codigos = {v["carpeta"] for v in vivas if v["estado"] not in ("retirada",)}
    total_universo = db.query(func.count(UnidadInventario.id)).scalar() or 0
    abiertas = [v for v in vivas if v["estado"] not in ("hecha", "retirada")]
    hitos = [avance_de_hito(db, h) for h in
             db.query(HitoCronograma).order_by(HitoCronograma.fecha_fin, HitoCronograma.id).all()]
    return {
        "fecha": hoy().isoformat(),
        "kpis": {
            "universo": total_universo, "asignadas": len(vivas),
            "sin_asignar": max(0, total_universo - len(asignadas_codigos)),
            "hechas": sum(1 for v in vivas if v["estado"] == "hecha"),
            "abiertas": len(abiertas),
            "vencidas": sum(1 for v in vivas if v["vencida"]),
            "colgadas": sum(1 for v in vivas if v["colgada"]),
            "devueltas": sum(1 for v in vivas if v["estado"] == "devuelta"),
        },
        "estados": {e: sum(1 for v in vivas if v["estado"] == e)
                    for e in ("pendiente", "en_curso", "devuelta", "sin_documento", "hecha")},
        "embudo": embudo, "personas": personas, "dias_actividad": dias, "hitos": hitos,
        "colgadas": [v for v in vivas if v["colgada"] or v["vencida"]][:100],
    }
