"""
El Contrato 733 de 2026 hecho dato: plazo, metros lineales, lotes, obligaciones, garantías,
riesgo de multa y alertas.

Todo lo que se puede medir sale de la base de datos y no de un contador aparte. Lo que solo
una persona puede afirmar (que el plan se aprobó, que el supervisor recibió un lote) se
registra a mano, con quién y cuándo.

Metros lineales. El contrato se paga por metro lineal «realmente intervenido y recibido a
satisfacción». Una caja X-200 ocupa 0,25 metros lineales (cuatro cajas por metro), así que un
metro lineal intervenido es cuatro cajas con TODAS sus carpetas intervenidas. Se muestran dos
cifras: los metros lineales completos (cajas cerradas, que es lo que se puede cobrar) y los
equivalentes (proporcional al avance dentro de cada caja, que es lo que mide el ritmo).
No se calculan a partir de los folios: las cajas no vienen llenas por igual y los folios dan
una cifra que no coincide con la que el Servicio Geológico mide.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from geology.dominio import seguimiento as seg
from geology.dominio.estados import Estado

PARAMETROS = {
    "contrato_numero": ("Contrato", "733 de 2026"),
    "proceso": ("Proceso de selección", "SGC-SAMC-006-2026"),
    "contratante": ("Contratante", "Servicio Geológico Colombiano"),
    "contratista": ("Contratista", "HOMETIC S.A.S."),
    "nit": ("NIT del contratista", "901.705.424-4"),
    "representante": ("Representante legal", "Hasson Javier González Verano"),
    "supervisor": ("Supervisor del contrato", "Carlos Alberto Díaz Corredor"),
    "direccion": ("Dirección del contratista", "Calle 77 # 69B-56, Ferias, Bogotá D.C."),
    "telefono": ("Teléfono del contratista", "323 6567087"),
    "correo": ("Correo del contratista", "info@hometicsa.com"),
    "valor": ("Valor del contrato (IVA incluido)", "314576987"),
    "fecha_inicio": ("Fecha del acta de inicio", "2026-07-08"),
    "fecha_fin": ("Fecha de terminación", "2026-12-31"),
    "ml_contrato": ("Metros lineales que se pagan (base de pago del contrato)", "175"),
    "ml_base": ("Metros lineales a intervenir en total (los pagados más el valor agregado sin costo)", "255"),
    "valor_ml": ("Valor por metro lineal intervenido, IVA incluido", "1797582.78"),
    "iva_pct": ("IVA incluido en el valor, %", "19"),
    "ml_por_caja": ("Metros lineales por caja X-200", "0.25"),
    "rango_intervenida": ("Una carpeta cuenta como intervenida desde el estado número", "4"),
    "multa_por_mil": ("Multa diaria, por mil del valor", "2"),
    "tope_multa_pct": ("Tope de las multas, % del valor", "20"),
    "penal_pct": ("Cláusula penal, % del valor", "20"),
    "error_maximo_pct": ("Error máximo por lote, %", "10"),
    "dias_ajuste": ("Días hábiles para atender observaciones", "5"),
}

# Festivos de Colombia entre octubre de 2026 y marzo de 2027, para contar días hábiles de los
# procesos de eliminación. Es una aproximación: el Servicio Geológico puede tener su propio
# calendario administrativo.
FESTIVOS = {
    date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16), date(2026, 12, 8),
    date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 11), date(2027, 3, 22),
    date(2027, 3, 25), date(2027, 3, 26),
}

LOTES_DEL_PLAN = [
    (1, "Lote 1", date(2026, 7, 16), date(2026, 8, 7), 30),
    (2, "Lote 2", date(2026, 8, 8), date(2026, 9, 7), 50),
    (3, "Lote 3", date(2026, 9, 8), date(2026, 10, 7), 53),
    (4, "Lote 4", date(2026, 10, 8), date(2026, 11, 7), 51),
    (5, "Lote 5", date(2026, 11, 8), date(2026, 12, 7), 51),
    (6, "Lote 6", date(2026, 12, 8), date(2026, 12, 18), 20),
]

# Las 19 obligaciones específicas de la cláusula décima segunda, resumidas.
OBLIGACIONES = [
    (1, "Plan de trabajo y cronograma", "Presentarlos dentro de los 5 días hábiles siguientes al acta de inicio, para aprobación del supervisor."),
    (2, "Recibo de las cajas", "Recibir del SGC, con verificación y punteo contra inventarios, hasta 175 ML (700 cajas X-200), dejando acta de recibo."),
    (3, "Traslado, custodia y retorno", "Trasladar las cajas con cadena de custodia y retornarlas al archivo central al terminar."),
    (4, "Fichas técnicas por proceso", "Una ficha por cada proceso archivístico: clasificación, ordenación, descripción, valoración y disposición final."),
    (5, "Organización técnica", "Organizar los metros lineales según el anexo técnico, las TVD y la normativa del AGN."),
    (6, "FUID por periodos y disposición final", "Formato Único de Inventario Documental de lo organizado, por periodo y disposición final."),
    (7, "FUID de eliminación y sustentación", "FUID de lo sujeto a eliminación, informe técnico, presentación y sustentación ante el Comité Institucional de Gestión y Desempeño."),
    (8, "Correcciones del supervisor", "Atender las correcciones, ajustes o mejoras que pida el supervisor."),
    (9, "Inventario de documentos de apoyo", "Inventario de los documentos facilitativos o de apoyo identificados."),
    (10, "Base descriptiva ISAD(G)", "Base de datos de los expedientes de conservación total que se transfieren."),
    (11, "Cajas, carpetas y unidades de conservación", "Suministrarlas con las especificaciones del SGC y del AGN."),
    (12, "Digitalización", "Digitalizar lo que las TVD requieran, con calidad, integridad y entrega en los formatos definidos."),
    (13, "Informe técnico final", "Informe de organización, valoración, selección, eliminación y transferencia, con resultados cuantitativos y cualitativos."),
    (14, "Hojas de control y rótulos", "Elaborar e instalar hojas de control y rótulos de cajas y carpetas."),
    (15, "Equipo mínimo de trabajo", "Disponer del equipo mínimo con perfiles idóneos y experiencia certificada."),
    (16, "Disponibilidad del personal", "Garantizar la disponibilidad permanente del personal."),
    (17, "Equipos, mobiliario y elementos", "Proveer equipos tecnológicos, puntos de red, mobiliario, herramientas y elementos de protección."),
    (18, "Reuniones de seguimiento", "Asistir a las reuniones convocadas por el supervisor."),
    (19, "Informes mensuales", "Informes mensuales de ejecución sobre la implementación de las TVD, metas, dificultades y acciones correctivas."),
]


# ---------------------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------------------
def parametros(db: Session) -> dict:
    from geology.modelos import ParametroContrato
    p = {k: v[1] for k, v in PARAMETROS.items()}
    for fila in db.query(ParametroContrato).all():
        if fila.clave in p:
            p[fila.clave] = fila.valor
    return p


def guardar_parametro(db: Session, clave: str, valor: str) -> None:
    from geology.modelos import ParametroContrato
    if clave not in PARAMETROS:
        raise ValueError("Parámetro desconocido.")
    valor = (valor or "").strip()
    if not valor:
        raise ValueError("El valor no puede quedar vacío.")
    try:
        _validar(clave, valor)
    except ValueError:
        raise ValueError("El valor no es válido: las fechas van como AAAA-MM-DD y las cantidades como número.")
    valor = valor.replace(",", ".") if clave in _NUMEROS else valor
    fila = db.get(ParametroContrato, clave)
    if fila:
        fila.valor = valor
    else:
        db.add(ParametroContrato(clave=clave, valor=valor))
    db.flush()


_NUMEROS = ("valor", "ml_contrato", "ml_base", "valor_ml", "iva_pct", "ml_por_caja", "multa_por_mil",
            "tope_multa_pct", "penal_pct", "error_maximo_pct")


def _validar(clave: str, valor: str) -> None:
    if clave.startswith("fecha_"):
        date.fromisoformat(valor)
    elif clave in _NUMEROS:
        float(valor.replace(",", "."))
    elif clave in ("rango_intervenida", "dias_ajuste"):
        int(valor)


def _f(p: dict, clave: str) -> float:
    return float(str(p[clave]).replace(",", "."))


def _d(p: dict, clave: str) -> date:
    return date.fromisoformat(p[clave])


# ---------------------------------------------------------------------------------------
# Días hábiles con festivos
# ---------------------------------------------------------------------------------------
def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in FESTIVOS


def dias_habiles(desde: date, hasta: date) -> int:
    """Días hábiles entre dos fechas, ambas incluidas, sin contar festivos."""
    n, d = 0, desde
    while d <= hasta:
        n += es_habil(d)
        d += timedelta(days=1)
    return n


def sumar_habiles(desde: date, n: int) -> date:
    """La fecha en que se cumplen n días hábiles después de «desde» (sin contar el propio día)."""
    d, contados = desde, 0
    while contados < n:
        d += timedelta(days=1)
        if es_habil(d):
            contados += 1
    return d


def agregar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    ultimo = [31, 29 if anio % 4 == 0 and (anio % 100 or anio % 400 == 0) else 28,
              31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    return date(anio, mes, min(d.day, ultimo))


# ---------------------------------------------------------------------------------------
# Semillas
# ---------------------------------------------------------------------------------------
def sembrar(db: Session) -> None:
    """Crea los lotes del plan y las 19 obligaciones la primera vez. No pisa nada existente."""
    from geology.modelos import LoteContrato, ObligacionContrato
    if not db.query(LoteContrato.id).first():
        for n, nombre, ini, fin, ml in LOTES_DEL_PLAN:
            db.add(LoteContrato(numero=n, nombre=nombre, fecha_inicio=ini, fecha_fin=fin, meta_ml=ml))
    existentes = {n for (n,) in db.query(ObligacionContrato.numero).all()}
    for numero, _, _ in OBLIGACIONES:
        if numero not in existentes:
            db.add(ObligacionContrato(numero=numero, estado="pendiente"))
    db.flush()


# ---------------------------------------------------------------------------------------
# Metros lineales
# ---------------------------------------------------------------------------------------
def _primera_vez(db: Session, rango: int) -> dict:
    """Para cada carpeta, el día en que llegó por primera vez al estado que cuenta como intervenida."""
    from geology.modelos import Expediente, Trazabilidad
    por_estado = {e for e, r in seg.RANGO.items() if r >= rango}
    primera: dict[str, date] = {}
    q = (db.query(Expediente.codigo_carpeta, Trazabilidad.fecha)
           .join(Trazabilidad, Trazabilidad.expediente_id == Expediente.id)
           .filter(Trazabilidad.estado_nuevo.in_(por_estado)))
    for codigo, fecha in q.yield_per(2000):
        d = fecha.date() if hasattr(fecha, "date") else fecha
        if codigo not in primera or d < primera[codigo]:
            primera[codigo] = d
    return primera


def metros_lineales(db: Session, a_la_fecha: date | None = None) -> dict:
    """
    Metros lineales intervenidos: completos (cajas con todas sus carpetas) y equivalentes.

    Con «a_la_fecha» devuelve cómo estaban ese día, reconstruido con la bitácora: una carpeta
    cuenta desde el día en que llegó por primera vez al estado de intervenida. Sirve para sacar
    lo que se hizo en un mes o en un lote restando dos cortes.
    """
    from geology.modelos import Expediente, UnidadInventario
    p = parametros(db)
    rango = int(p["rango_intervenida"])
    ml_caja = _f(p, "ml_por_caja")
    inicio = _d(p, "fecha_inicio")
    primera = _primera_vez(db, rango) if a_la_fecha else {}

    cajas: dict[str, list[int]] = {}
    q = (db.query(UnidadInventario.caja_origen, UnidadInventario.codigo_carpeta, Expediente.estado)
           .outerjoin(Expediente, Expediente.codigo_carpeta == UnidadInventario.codigo_carpeta))
    carpetas = hechas = 0
    for caja, codigo, estado in q.yield_per(2000):
        carpetas += 1
        ok = estado != Estado.RETIRADO.value and seg.RANGO.get(estado, -1) >= rango
        if ok and a_la_fecha:
            ok = primera.get(codigo, inicio) <= a_la_fecha
        hechas += ok
        if not caja:
            continue
        c = cajas.setdefault(caja, [0, 0])
        c[0] += 1
        c[1] += ok
    completas = sum(1 for t, h in cajas.values() if t and h == t)
    equivalente = sum(ml_caja * h / t for t, h in cajas.values() if t)
    base = _f(p, "ml_base")
    return {
        "cajas_en_inventario": len(cajas), "cajas_completas": completas,
        "ml_completos": round(completas * ml_caja, 2), "ml_equivalentes": round(equivalente, 2),
        "ml_base": base, "ml_inventario": round(len(cajas) * ml_caja, 2),
        "carpetas": carpetas, "carpetas_intervenidas": hechas,
        "porcentaje": round(100 * equivalente / base, 1) if base else 0,
    }


def ml_del_periodo(db: Session, desde: date, hasta: date) -> dict:
    """Metros lineales intervenidos entre dos fechas (incluidas), por diferencia de cortes."""
    antes = metros_lineales(db, desde - timedelta(days=1))
    despues = metros_lineales(db, hasta)
    return {"ml": round(despues["ml_equivalentes"] - antes["ml_equivalentes"], 2),
            "ml_completos": round(despues["ml_completos"] - antes["ml_completos"], 2),
            "carpetas": despues["carpetas_intervenidas"] - antes["carpetas_intervenidas"],
            "al_cierre": despues}


# ---------------------------------------------------------------------------------------
# Plan por lotes
# ---------------------------------------------------------------------------------------
def plan_a_la_fecha(lotes: list, dia: date) -> float:
    """Metros lineales que el plan exige tener a una fecha: lineal por días hábiles dentro de cada lote."""
    total = 0.0
    for lt in lotes:
        if dia >= lt.fecha_fin:
            total += lt.meta_ml
        elif dia >= lt.fecha_inicio:
            tramo = max(1, seg.dias_habiles(lt.fecha_inicio, lt.fecha_fin))
            hechos = seg.dias_habiles(lt.fecha_inicio, dia)
            total += lt.meta_ml * min(1.0, hechos / tramo)
    return total


def _lotes(db: Session) -> list:
    from geology.modelos import LoteContrato
    return db.query(LoteContrato).order_by(LoteContrato.numero).all()


def lote_de(db: Session, dia: date):
    for lt in _lotes(db):
        if lt.fecha_inicio <= dia <= lt.fecha_fin:
            return lt
    return None


# ---------------------------------------------------------------------------------------
# Garantías
# ---------------------------------------------------------------------------------------
def garantias(p: dict) -> list[dict]:
    valor, fin = _f(p, "valor"), _d(p, "fecha_fin")
    cumpl = agregar_meses(fin, 4)
    return [
        {"amparo": "Cumplimiento del contrato", "porcentaje": 20, "monto": round(valor * .20),
         "vigencia": "Plazo de ejecución y cuatro meses más; en todo caso hasta la liquidación.",
         "hasta": cumpl.isoformat()},
        {"amparo": "Calidad del servicio prestado", "porcentaje": 20, "monto": round(valor * .20),
         "vigencia": "Cuatro meses contados desde el vencimiento de la garantía de cumplimiento (lectura de la cláusula séptima; confirmar con la póliza).",
         "hasta": agregar_meses(cumpl, 4).isoformat()},
        {"amparo": "Pago de salarios, prestaciones sociales e indemnizaciones laborales", "porcentaje": 5,
         "monto": round(valor * .05),
         "vigencia": "Duración del contrato y tres años más. La minuta dice «diez por ciento (5 %)»: la póliza debe decir 5 %.",
         "hasta": agregar_meses(fin, 36).isoformat()},
    ]


# ---------------------------------------------------------------------------------------
# Resumen y alertas
# ---------------------------------------------------------------------------------------
def resumen(db: Session) -> dict:
    from geology.modelos import ObligacionContrato, ObservacionSupervision, ProcesoEliminacion
    sembrar(db)
    p = parametros(db)
    hoy = date.today()
    ini, fin = _d(p, "fecha_inicio"), _d(p, "fecha_fin")
    valor, base = _f(p, "valor"), _f(p, "ml_base")
    ml = metros_lineales(db)
    lotes = _lotes(db)

    plan_hoy = plan_a_la_fecha(lotes, hoy)
    atraso = max(0.0, plan_hoy - ml["ml_equivalentes"])
    restantes_ml = max(0.0, base - ml["ml_equivalentes"])
    habiles = dias_habiles(max(hoy, ini), fin)
    ritmo_req = restantes_ml / habiles if habiles else restantes_ml

    # Se paga por los metros del contrato (175), no por los 255 que se intervienen: los 80 de
    # más son valor agregado sin costo y se entregan al final.
    pagados = _f(p, "ml_contrato")
    valor_ml = _f(p, "valor_ml") or (valor / pagados if pagados else 0)
    from geology.dominio import cobro as _cobro
    _c = _cobro.calcular(db)
    facturado = _c["valor_facturado"] or sum((lt.valor_facturado or 0) for lt in lotes)
    cobrable = min(ml["ml_completos"], pagados) * valor_ml

    acumulado, lotes_sal = 0.0, []
    for lt in lotes:
        acumulado += lt.meta_ml
        vencido = hoy > lt.fecha_fin
        lotes_sal.append({
            "id": lt.id, "numero": lt.numero, "nombre": lt.nombre, "inicio": lt.fecha_inicio.isoformat(),
            "fin": lt.fecha_fin.isoformat(), "meta_ml": lt.meta_ml, "meta_acumulada": acumulado,
            "cumplido": ml["ml_equivalentes"] + 0.001 >= acumulado,
            "vencido": vencido, "recibido_en": lt.recibido_en.isoformat() if lt.recibido_en else None,
            "facturado_en": lt.facturado_en.isoformat() if lt.facturado_en else None,
            "valor_facturado": lt.valor_facturado, "nota": lt.nota,
        })

    multa_dia = valor * _f(p, "multa_por_mil") / 1000
    tope_multa = valor * _f(p, "tope_multa_pct") / 100

    obs_abiertas = db.query(ObservacionSupervision).filter(ObservacionSupervision.estado == "abierta").all()
    obs_vencidas = [o for o in obs_abiertas if o.fecha_limite < hoy]

    alertas: list[dict] = []
    dias_rest = (fin - hoy).days
    if dias_rest <= 30:
        alertas.append({"nivel": "amarillo", "texto": f"Quedan {dias_rest} días para el cierre del contrato ({fin.isoformat()})."})
    if atraso > 0.5:
        alertas.append({"nivel": "rojo" if atraso > 5 else "amarillo",
                        "texto": f"Hay un atraso de {atraso:.1f} ML frente al plan. Cada día de mora en el cumplimiento puede costar una multa de ${multa_dia:,.0f} (tope ${tope_multa:,.0f})."})
    if obs_vencidas:
        alertas.append({"nivel": "rojo", "texto": f"{len(obs_vencidas)} observación(es) de la supervisión pasaron su plazo de {p['dias_ajuste']} días hábiles."})
    for lt in lotes:
        if hoy > lt.fecha_fin + timedelta(days=7) and not lt.recibido_en:
            alertas.append({"nivel": "amarillo", "texto": f"{lt.nombre} terminó el {lt.fecha_fin.isoformat()} y aún no registra el recibo a satisfacción."})
    proceso = db.query(ProcesoEliminacion).order_by(ProcesoEliminacion.id.desc()).first()
    if not proceso and hoy >= date(2026, 10, 1):
        alertas.append({"nivel": "amarillo", "texto": "El plan de trabajo inicia el 1 de octubre la propuesta de eliminación y aún no hay una creada."})
    if proceso and not proceso.fecha_sustentacion and hoy > date(2026, 11, 15):
        alertas.append({"nivel": "rojo", "texto": "El plan prevé el aval del Comité antes del 15 de noviembre y la sustentación aún no tiene fecha."})
    if sum(l.meta_ml for l in lotes) != base:
        alertas.append({"nivel": "amarillo", "texto": f"Las metas de los lotes suman {sum(l.meta_ml for l in lotes):g} ML y el contrato a intervenir es {base:g}."})
    if ml["cajas_en_inventario"] and ml["cajas_en_inventario"] * _f(p, "ml_por_caja") < base * .99:
        alertas.append({"nivel": "amarillo", "texto": f"El inventario cargado tiene {ml['cajas_en_inventario']} cajas ({ml['ml_inventario']:g} ML) y la meta es {base:g} ML."})

    estados = dict(db.query(ObligacionContrato.numero, ObligacionContrato.estado).all())
    return {
        "contrato": {k: p[k] for k in ("contrato_numero", "proceso", "contratante", "contratista", "supervisor")},
        "valor": valor, "inicio": ini.isoformat(), "fin": fin.isoformat(),
        "dias_totales": (fin - ini).days, "dias_transcurridos": max(0, (min(hoy, fin) - ini).days),
        "dias_restantes": max(0, dias_rest), "habiles_restantes": habiles,
        "ml_pagados": pagados, "ml_valor_agregado": round(max(0.0, base - pagados), 2),
        "ml_valor_agregado_hecho": round(max(0.0, ml["ml_completos"] - pagados), 2),
        "ml": ml, "plan_a_hoy": round(plan_hoy, 2), "atraso_ml": round(atraso, 2),
        "ritmo_requerido_ml_por_dia": round(ritmo_req, 2),
        "ritmo_minimo_contractual_ml_mes": round(_f(p, "ml_contrato") / 6, 2),
        "finanzas": {"valor_por_ml": round(valor_ml), "cobrable_estimado": round(cobrable),
                     "facturado": round(facturado), "por_facturar": round(max(0, cobrable - facturado)),
                     "avance_financiero_pct": round(100 * facturado / valor, 1) if valor else 0},
        "multa": {"por_dia": round(multa_dia), "tope": round(tope_multa),
                  "penal": round(valor * _f(p, "penal_pct") / 100)},
        "garantias": garantias(p), "lotes": lotes_sal, "alertas": alertas,
        "obligaciones_cumplidas": sum(1 for e in estados.values() if e == "cumplida"),
        "observaciones_abiertas": len(obs_abiertas), "observaciones_vencidas": len(obs_vencidas),
    }


def indicador_de_obligacion(db: Session, numero: int) -> str:
    """Lo que la plataforma puede decir por sí sola de una obligación."""
    from sqlalchemy import func
    from geology.modelos import Caja, Expediente, UnidadInventario
    if numero in (5, 14):
        ml = metros_lineales(db)
        return f"{ml['carpetas_intervenidas']} de {ml['carpetas']} carpetas intervenidas ({ml['ml_equivalentes']:g} de {ml['ml_base']:g} ML)."
    if numero == 2:
        return f"{db.query(func.count(func.distinct(UnidadInventario.caja_origen))).scalar() or 0} cajas en el inventario de origen."
    if numero in (6, 10):
        n = db.query(func.count(Expediente.id)).filter(Expediente.estado.in_(
            [Estado.DESCRIPCION_VALIDADA.value, Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value])).scalar() or 0
        return f"{n} descripciones validadas o archivadas."
    if numero == 12:
        from geology.modelos import Archivo
        return f"{db.query(func.count(Archivo.id)).scalar() or 0} archivos digitalizados cargados."
    if numero == 3:
        return f"{db.query(func.count(Caja.id)).filter(Caja.cerrada.is_(True)).scalar() or 0} cajas definitivas cerradas."
    return ""
