"""
Cobro del contrato 733 de 2026: pagos mensuales vencidos, cuenta de cobro y soportes.

Lo que dijo el Servicio Geológico Colombiano sobre el cobro (cláusula cuarta y comunicación de
la supervisión):

  - El valor total es $314.576.987 por 175 metros lineales con las TVD, IVA incluido: el valor
    por metro lineal es $1.797.582,78.
  - Se paga por metros lineales realmente intervenidos y recibidos a satisfacción, mes vencido.
    La proyección entregada es de 30, 40, 40 y 65 metros lineales, pagados en octubre,
    noviembre, diciembre y enero.
  - Antes de radicar cada factura se envía la prefactura para validación y aprobación, y los
    metros lineales reportados tienen que corresponder a los intervenidos y recibidos.
  - La plataforma no cobra por los 80 metros lineales de valor agregado: se entregan al final
    y no tienen costo. Por eso el cobro se topa en 175.

Aquí se calcula cuánto sugiere la plataforma cobrar en cada pago, se arma la cuenta de cobro
(prefactura), la relación de metros lineales intervenidos y aprobados, y el formato F-FIN-007.
Todo lo calculado es una propuesta: la administradora decide cuántos metros lineales cobra.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from geology.dominio import contrato as ct
from geology.dominio.documentos import (MESES, PEND, fecha_larga, h1, h2, h3, li, moneda, num, p, tabla)

# Proyección de pagos entregada por el Servicio Geológico (mes vencido).
PAGOS_SGC = [
    (1, "Pago 1 · septiembre de 2026", date(2026, 7, 8), date(2026, 9, 30), 30),
    (2, "Pago 2 · octubre de 2026", date(2026, 10, 1), date(2026, 10, 31), 40),
    (3, "Pago 3 · noviembre de 2026", date(2026, 11, 1), date(2026, 11, 30), 40),
    (4, "Pago 4 · diciembre de 2026", date(2026, 12, 1), date(2026, 12, 31), 65),
]
ESTADOS = [("proyectado", "Proyectado"), ("prefactura", "Prefactura enviada"), ("aprobado", "Prefactura aprobada"),
           ("facturado", "Facturado"), ("radicado", "Radicado en el SGC"), ("pagado", "Pagado")]

# Soportes del trámite de cobro: (clave, texto, automático)
SOPORTES = [
    ("prefactura", "Prefactura validada y aprobada por la supervisión antes de radicar", True),
    ("informes", "Informe(s) mensual(es) de ejecución del periodo", True),
    ("relacion", "Relación de metros lineales efectivamente intervenidos y aprobados", True),
    ("recibo", "Certificación de cumplimiento y acta de recibo a satisfacción del supervisor", True),
    ("f_fin_007", "Formato F-FIN-007 diligenciado y firmado por el supervisor", False),
    ("factura", "Factura electrónica validada por la DIAN (con IVA)", True),
    ("seguridad_social", "Certificación de aportes a seguridad social y parafiscales (representante legal o revisor fiscal, artículo 50 de la Ley 789 de 2002)", False),
    ("rut", "RUT actualizado", False),
    ("banco", "Certificación bancaria", False),
    ("contrato", "Copia del contrato, modificaciones y anexos (primer pago)", False),
]

_UNIDADES = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
             "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
             "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
             "veintiocho", "veintinueve"]
_DECENAS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CENTENAS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos",
             "setecientos", "ochocientos", "novecientos"]


def _menos_de_mil(n: int) -> str:
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    partes = [_CENTENAS[c]] if c else []
    if r < 30:
        if r:
            partes.append(_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        partes.append(_DECENAS[d] + (f" y {_UNIDADES[u]}" if u else ""))
    return " ".join(partes)


def a_letras(n: int) -> str:
    """Un entero en letras, en español, hasta 999.999.999.999 (sin apócope en «uno» final)."""
    n = int(n)
    if n == 0:
        return "cero"
    millones_mil, resto = divmod(n, 1_000_000_000)
    partes: list[str] = []
    if millones_mil:
        partes.append(a_letras(millones_mil) + " mil")
    millones, resto = divmod(resto, 1_000_000)
    if millones:
        partes.append("un millón" if millones == 1 else _menos_de_mil_mil(millones) + " millones")
    miles, unidades = divmod(resto, 1000)
    if miles:
        partes.append("mil" if miles == 1 else _menos_de_mil(miles).replace("veintiuno", "veintiún").replace("uno", "un") + " mil")
    if unidades:
        partes.append(_menos_de_mil(unidades))
    return " ".join(partes).replace("  ", " ").strip()


def _menos_de_mil_mil(n: int) -> str:
    return _menos_de_mil(n).replace("veintiuno", "veintiún").replace(" y uno", " y un") if n % 10 == 1 else _menos_de_mil(n)


def valor_en_letras(valor: float) -> str:
    entero = int(round(valor))
    return f"{a_letras(entero).upper()} PESOS M/CTE"


# ---------------------------------------------------------------------------------------
def sembrar(db: Session) -> None:
    from geology.modelos import PagoContrato
    if db.query(PagoContrato.id).first():
        return
    for n, nombre, d, h, ml in PAGOS_SGC:
        db.add(PagoContrato(numero=n, nombre=nombre, periodo_desde=d, periodo_hasta=h, ml_proyectados=ml))
    db.flush()


def _pagos(db: Session) -> list:
    from geology.modelos import PagoContrato
    sembrar(db)
    return db.query(PagoContrato).order_by(PagoContrato.numero).all()


def calcular(db: Session) -> dict:
    """
    Lo que cada pago podría cobrar hoy, con los metros lineales completos intervenidos al
    cierre de su periodo, descontando lo ya cobrado en los pagos anteriores y topando en los
    metros lineales que se pagan.
    """
    pr = ct.parametros(db)
    pagados = float(pr["ml_contrato"])
    valor_ml = float(pr["valor_ml"])
    total = float(pr["valor"])
    iva_pct = float(pr["iva_pct"])
    hoy = date.today()
    filas, previo_ml, previo_valor = [], 0.0, 0.0
    for pg in _pagos(db):
        corte = min(pg.periodo_hasta, hoy)
        ml = ct.metros_lineales(db, corte)
        acum = ml["ml_completos"]
        sugerido = round(max(0.0, min(acum, pagados) - previo_ml), 2)
        efectivo = pg.ml_a_cobrar if pg.ml_a_cobrar is not None else sugerido
        efectivo = round(max(0.0, min(efectivo, pagados - previo_ml)), 2)
        valor = round(efectivo * valor_ml)
        if efectivo and previo_ml + efectivo >= pagados - 0.001:
            valor = round(total - previo_valor)           # el último pago cierra en el valor total sin centavos sueltos
        base = round(valor / (1 + iva_pct / 100))
        filas.append({
            "numero": pg.numero, "nombre": pg.nombre, "desde": pg.periodo_desde.isoformat(), "hasta": pg.periodo_hasta.isoformat(),
            "ml_proyectados": pg.ml_proyectados, "valor_proyectado": round(pg.ml_proyectados * valor_ml),
            "ml_acumulados_al_corte": acum, "ml_sugeridos": sugerido, "ml_a_cobrar": efectivo,
            "editado": pg.ml_a_cobrar is not None, "valor": valor, "valor_antes_iva": base, "iva": valor - base,
            "ml_acumulado_cobrado": round(previo_ml + efectivo, 2), "estado": pg.estado,
            "prefactura_enviada": pg.prefactura_enviada.isoformat() if pg.prefactura_enviada else None,
            "prefactura_aprobada": pg.prefactura_aprobada.isoformat() if pg.prefactura_aprobada else None,
            "recibo_satisfaccion": pg.recibo_satisfaccion.isoformat() if pg.recibo_satisfaccion else None,
            "factura_numero": pg.factura_numero or "", "factura_fecha": pg.factura_fecha.isoformat() if pg.factura_fecha else None,
            "radicado_en": pg.radicado_en.isoformat() if pg.radicado_en else None,
            "pagado_en": pg.pagado_en.isoformat() if pg.pagado_en else None, "valor_pagado": pg.valor_pagado,
            "soportes": pg.soportes or {}, "nota": pg.nota or "",
            "periodo_cerrado": hoy > pg.periodo_hasta,
        })
        previo_ml += efectivo
        previo_valor += valor
    ml_hoy = ct.metros_lineales(db)
    cobrado = sum(f["valor"] for f in filas if f["estado"] in ("facturado", "radicado", "pagado"))
    return {
        "pagos": filas, "valor_ml": valor_ml, "ml_pagados": pagados, "valor_contrato": total, "iva_pct": iva_pct,
        "ml_cobrados_total": round(previo_ml, 2), "valor_a_cobrar_total": round(previo_valor),
        "valor_facturado": round(cobrado), "valor_pagado": round(sum(f["valor_pagado"] or 0 for f in filas)),
        "saldo_ml_por_cobrar": round(max(0.0, pagados - previo_ml), 2),
        "ml_completos_hoy": ml_hoy["ml_completos"],
        "ml_valor_agregado_hecho": round(max(0.0, ml_hoy["ml_completos"] - pagados), 2),
        "ml_valor_agregado": round(max(0.0, float(pr["ml_base"]) - pagados), 2),
        "proyeccion_suma_ml": sum(f["ml_proyectados"] for f in filas),
    }


def _pago(db: Session, numero: int):
    for pg in _pagos(db):
        if pg.numero == numero:
            return pg
    raise ValueError(f"No existe el pago {numero}.")


def _fila(db: Session, numero: int) -> dict:
    return next(f for f in calcular(db)["pagos"] if f["numero"] == numero)


def _nombre_periodo(desde: date, hasta: date) -> str:
    return f"del {fecha_larga(desde)} al {fecha_larga(hasta)}"


# ---------------------------------------------------------------------------------------
# Cajas completas con la fecha en que quedaron completas
# ---------------------------------------------------------------------------------------
def cajas_completas(db: Session, hasta: date) -> list[dict]:
    from geology.modelos import Expediente, UnidadInventario
    from geology.dominio import seguimiento as seg
    from geology.dominio.estados import Estado
    pr = ct.parametros(db)
    rango = int(pr["rango_intervenida"])
    inicio = date.fromisoformat(pr["fecha_inicio"])
    primera = ct._primera_vez(db, rango)
    q = (db.query(UnidadInventario.caja_origen, UnidadInventario.codigo_carpeta, UnidadInventario.folios,
                  UnidadInventario.periodo, Expediente.estado, Expediente.volumen_folios)
           .outerjoin(Expediente, Expediente.codigo_carpeta == UnidadInventario.codigo_carpeta))
    cajas: dict[str, dict] = {}
    for caja, codigo, folios, periodo, estado, folios_hoja in q.yield_per(2000):
        if not caja:
            continue
        c = cajas.setdefault(caja, {"caja": caja, "carpetas": 0, "folios": 0, "periodos": set(), "ok": 0, "fecha": inicio})
        c["carpetas"] += 1
        c["folios"] += (folios_hoja or folios or 0)
        if periodo:
            c["periodos"].add(periodo)
        ok = estado != Estado.RETIRADO.value and seg.RANGO.get(estado, -1) >= rango
        if ok:
            c["ok"] += 1
            c["fecha"] = max(c["fecha"], primera.get(codigo, inicio))
    salida = [c for c in cajas.values() if c["carpetas"] and c["ok"] == c["carpetas"] and c["fecha"] <= hasta]
    salida.sort(key=lambda c: (c["fecha"], c["caja"]))
    return salida


# ---------------------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------------------
def cuenta_de_cobro(db: Session, numero: int) -> tuple[str, dict]:
    pr = ct.parametros(db)
    c = calcular(db)
    f = next((x for x in c["pagos"] if x["numero"] == numero), None)
    if not f:
        raise ValueError(f"No existe el pago {numero}.")
    desde, hasta = date.fromisoformat(f["desde"]), date.fromisoformat(f["hasta"])
    titulo = f"Cuenta de cobro · {f['nombre']}"
    previos = [x for x in c["pagos"] if x["numero"] < numero]
    b = [h1(titulo),
         p("Prefactura y cuenta de cobro para validación y aprobación de la supervisión antes de radicar la factura "
           "(cláusula cuarta del contrato). Los metros lineales relacionados corresponden a los intervenidos, verificados "
           f"y recibidos a satisfacción en el periodo. Generada el {fecha_larga(date.today())}."),
         h2("1. Datos del cobro"),
         tabla(["Campo", "Valor"], [
             ["Contratista", f"{pr['contratista']} · NIT {pr['nit']}"], ["Representante legal", pr["representante"]],
             ["Contratante", pr["contratante"]], ["Contrato", f"{pr['contrato_numero']} ({pr['proceso']})"],
             ["Supervisor", pr["supervisor"]], ["Pago", f"{numero} de {len(c['pagos'])}"],
             ["Periodo a pagar", _nombre_periodo(desde, hasta)],
             ["Forma de pago", "Mensual vencido, por metros lineales intervenidos y recibidos a satisfacción"]]),
         h2("2. Detalle de lo que se cobra"),
         tabla(["Concepto", "Metros lineales", "Valor por metro lineal (IVA incluido)", "Valor"], [
             [f"Intervención y entrega de metros lineales con las Tablas de Valoración Documental, periodo {_nombre_periodo(desde, hasta)}",
              num(f["ml_a_cobrar"]), moneda(c["valor_ml"]), moneda(f["valor"])],
             ["Valor antes de IVA", "", "", moneda(f["valor_antes_iva"])],
             [f"IVA ({c['iva_pct']:g} %)", "", "", moneda(f["iva"])],
             ["Valor total a pagar", "", "", moneda(f["valor"])]]),
         p(f"Son: {valor_en_letras(f['valor'])}."),
         p(PEND.format("confirmar con contabilidad el IVA aplicable y la discriminación de la factura")),
         h2("3. Base de pago y acumulado"),
         p(f"El contrato paga {num(c['ml_pagados'], 0)} metros lineales a {moneda(c['valor_ml'])} cada uno. Con este pago el cobro "
           f"acumulado es de {num(f['ml_acumulado_cobrado'])} metros lineales ({num(100 * f['ml_acumulado_cobrado'] / c['ml_pagados'], 1)} % de la base de pago). "
           f"Los {num(c['ml_valor_agregado'], 0)} metros lineales adicionales que ofrece el contratista como valor agregado no tienen costo, "
           "se entregan al final y no se incluyen en ningún cobro."),
         tabla(["Pago", "Periodo", "Metros lineales", "Valor"],
               [[x["numero"], f"{x['desde']} a {x['hasta']}", num(x["ml_a_cobrar"]), moneda(x["valor"])] for x in previos]
               + [[f"{numero} (este cobro)", f"{f['desde']} a {f['hasta']}", num(f["ml_a_cobrar"]), moneda(f["valor"])],
                  ["Acumulado", "", num(f["ml_acumulado_cobrado"]), moneda(sum(x["valor"] for x in previos) + f["valor"])]]),
         p(f"Valor del contrato: {moneda(c['valor_contrato'])}. Saldo por cobrar después de este pago: "
           f"{moneda(c['valor_contrato'] - sum(x['valor'] for x in previos) - f['valor'])}."),
         h2("4. Documentos que acompañan el cobro"),
         li(*[t for _, t, _ in SOPORTES]),
         h2("5. Firma"),
         tabla(["Presenta", "Revisa"], [[f"{pr['representante']}\nRepresentante legal\n{pr['contratista']}", f"{pr['supervisor']}\nSupervisor del contrato\n{pr['contratante']}"],
                                        ["Fecha: ____________", "Fecha: ____________"]])]
    return titulo, {"bloques": b, "meta": {"pago": str(numero)}}


def relacion_de_metros(db: Session, numero: int) -> tuple[str, dict]:
    pr = ct.parametros(db)
    c = calcular(db)
    f = next((x for x in c["pagos"] if x["numero"] == numero), None)
    if not f:
        raise ValueError(f"No existe el pago {numero}.")
    hasta = date.fromisoformat(f["hasta"])
    ml_caja = float(pr["ml_por_caja"])
    previas = round(sum(x["ml_a_cobrar"] for x in c["pagos"] if x["numero"] < numero), 2)
    completas = cajas_completas(db, min(hasta, date.today()))
    # Las primeras cajas ya se relacionaron en los pagos anteriores; la relación de este pago
    # son las que siguen, tantas como metros lineales se cobran.
    saltar = int(round(previas / ml_caja))
    tomar = int(round(f["ml_a_cobrar"] / ml_caja))
    de_este = completas[saltar:saltar + tomar]
    filas = [[i, x["caja"], x["carpetas"], x["folios"], ", ".join(sorted(x["periodos"])) or "—", x["fecha"].isoformat(), num(ml_caja)]
             for i, x in enumerate(de_este, start=1)]
    titulo = f"Relación de metros lineales · {f['nombre']}"
    b = [h1(titulo),
         p(f"Relación de los metros lineales efectivamente intervenidos y aprobados que respaldan el cobro del {f['nombre']} "
           f"(periodo {_nombre_periodo(date.fromisoformat(f['desde']), hasta)}). Cada caja de referencia X-200 equivale a {num(ml_caja)} "
           "metros lineales y se relaciona cuando todas sus carpetas están intervenidas. Generada el "
           f"{fecha_larga(date.today())}."),
         tabla(["Indicador", "Valor"], [
             ["Cajas X-200 relacionadas en este cobro", len(de_este)], ["Metros lineales de este cobro", num(f["ml_a_cobrar"])],
             ["Cajas completas intervenidas a la fecha de corte", len(completas)],
             ["Carpetas relacionadas", sum(x["carpetas"] for x in de_este)], ["Folios relacionados", sum(x["folios"] for x in de_este)]]),
         tabla(["N.º", "Caja de origen", "Carpetas", "Folios", "Periodo(s)", "Quedó completa el", "ML"], filas)
         if filas else p("Todavía no hay cajas completas para relacionar en este pago."),
         p("Esta relación sale del estado de cada carpeta en la plataforma. Los metros lineales se cobran solo cuando el supervisor "
           "los recibe a satisfacción; la lista puede ajustarse a lo que el supervisor apruebe."),
         ]
    if len(de_este) * ml_caja + 0.001 < f["ml_a_cobrar"]:
        b.append(p(f"Atención: la relación tiene {len(de_este)} cajas ({num(len(de_este) * ml_caja)} ML) y el cobro es de {num(f['ml_a_cobrar'])} ML. "
                   "Faltan cajas completas que respalden la diferencia; ajuste los metros lineales a cobrar o complete las cajas."))
    return titulo, {"bloques": b, "meta": {"pago": str(numero)}}


def informe_actividades(db: Session, numero: int) -> list[tuple[str, str]]:
    """(obligación, actividades del periodo) para la sección D del F-FIN-007."""
    f = _fila(db, numero)
    ml = f["ml_a_cobrar"]
    desde, hasta = date.fromisoformat(f["desde"]), date.fromisoformat(f["hasta"])
    por = {n: (t, x) for n, t, x in ct.OBLIGACIONES}
    periodo = f"{desde.isoformat()} a {hasta.isoformat()}"
    texto = {
        1: "Plan de trabajo y cronograma aprobados por la supervisión; asistencia a las reuniones de seguimiento convocadas.",
        2: "Recibo de las cajas X-200 con verificación y punteo contra el inventario del SGC; traslado con cadena de custodia.",
        4: "Fichas técnicas por actividad (identificación, clasificación, depuración, ordenación, foliación, descripción, inventario, valoración y disposición) del lote en ejecución.",
        5: f"Organización técnica de {num(ml)} metros lineales en el periodo ({periodo}), de acuerdo con el anexo técnico y las TVD.",
        6: "Formato Único de Inventario Documental de lo intervenido, por periodo y disposición final.",
        7: "Avance en el FUID de eliminación, informe técnico y presentación para el Comité Institucional de Gestión y Desempeño.",
        8: "Atención de las correcciones, ajustes y mejoras solicitadas por la supervisión dentro de los cinco días hábiles.",
        9: "Inventario de los documentos facilitativos o de apoyo identificados en la intervención.",
        10: "Base descriptiva ISAD(G) de los expedientes de conservación total.",
        11: "Suministro de cajas, carpetas y unidades de conservación con las especificaciones del SGC y del AGN.",
        12: "Digitalización de las series que las TVD requieren, con control de calidad y entrega en los formatos definidos.",
        13: "Informe técnico final (consolidación progresiva de resultados cuantitativos y cualitativos).",
        14: "Hojas de control y rótulos de cajas y carpetas elaborados e instalados.",
        15: "Equipo mínimo de trabajo con los perfiles contratados; disponibilidad permanente del personal; equipos y elementos suministrados; informe mensual de ejecución.",
    }
    grupos = [(1, [1, 18]), (2, [2, 3]), (3, [4]), (4, [5]), (5, [6]), (6, [7]), (7, [8]), (8, [9]), (9, [10]),
              (10, [11, 17]), (11, [12]), (12, [13]), (13, [14]), (14, [15, 16, 19])]
    salida = []
    for _, nums in grupos:
        rotulo = "; ".join(f"{n}. {por[n][0]}" for n in nums)
        clave = nums[0]
        salida.append((rotulo, texto.get(clave, "")))
    return salida


def datos_f_fin_007(db: Session, numero: int) -> dict:
    pr = ct.parametros(db)
    c = calcular(db)
    f = next((x for x in c["pagos"] if x["numero"] == numero), None)
    if not f:
        raise ValueError(f"No existe el pago {numero}.")
    ini, fin = date.fromisoformat(pr["fecha_inicio"]), date.fromisoformat(pr["fecha_fin"])
    meses = (fin.year - ini.year) * 12 + fin.month - ini.month
    d_extra = fin - ct.agregar_meses(ini, meses)
    plazo = f"{meses} meses y {d_extra.days} días" if d_extra.days else f"{meses} meses"
    previos = [x["valor_pagado"] or 0 for x in c["pagos"] if x["numero"] < numero]
    return {
        "dependencia": "Grupo de Relacionamiento con la Ciudadanía - Gestión Documental",
        "pago_numero": numero, "total_pagos": len(c["pagos"]), "pago_final": "X" if numero == len(c["pagos"]) else "",
        "razon_social": pr["contratista"], "nit": pr["nit"],
        "correo": pr.get("correo", ""), "telefono": pr.get("telefono", ""), "direccion": pr.get("direccion", ""),
        "contrato": pr["contrato_numero"].replace(" de ", "-"),
        "fecha_inicio": ini, "fecha_fin": fin, "plazo": plazo, "cesion": "NO", "novedades": "SIN NOVEDADES", "ciudad": "Bogotá D.C.",
        "periodo_desde": date.fromisoformat(f["desde"]), "periodo_hasta": date.fromisoformat(f["hasta"]),
        "valor_pago_total": f["valor"], "valor_inicial": float(pr["valor"]), "valor_antes_iva": f["valor_antes_iva"], "iva": f["iva"],
        "pagos_previos": previos,
        "objeto": ("Realizar la implementación (identificación, organización y descripción documental) de las Tablas de Valoración "
                   "Documental del Servicio Geológico Colombiano para aquellas series, subseries o asuntos cuya disposición final sea "
                   "conservación total, selección o eliminación, de acuerdo con los lineamientos establecidos por el Archivo General de la Nación."),
        "obligaciones": informe_actividades(db, numero),
        "valor_letras": valor_en_letras(f["valor"]),
        "factura": f["factura_numero"],
        "descripcion_factura": f"Intervención de {num(f['ml_a_cobrar'])} metros lineales con TVD, contrato {pr['contrato_numero']}, {f['nombre']}",
        "municipio_actividad": "BOGOTA D.C.",
    }


# ---------------------------------------------------------------------------------------
# Lista de soportes
# ---------------------------------------------------------------------------------------
def meses_del_periodo(desde: date, hasta: date) -> list[tuple[int, int]]:
    salida, d = [], date(desde.year, desde.month, 1)
    while d <= hasta:
        salida.append((d.year, d.month))
        d = ct.agregar_meses(d, 1)
    return salida


def lista_de_soportes(db: Session, numero: int) -> list[dict]:
    from geology.modelos import DocumentoContrato
    f = _fila(db, numero)
    desde, hasta = date.fromisoformat(f["desde"]), date.fromisoformat(f["hasta"])
    docs = {(d.tipo, d.clave): d for d in db.query(DocumentoContrato).filter(
        DocumentoContrato.tipo.in_(["informe_mensual", "cobro_cuenta", "cobro_relacion"])).all()}
    manual = f["soportes"] or {}
    meses = meses_del_periodo(desde, hasta)
    faltan = [f"{MESES[m - 1]} {a}" for a, m in meses if ("informe_mensual", f"{a}-{m:02d}") not in docs]
    cuenta = docs.get(("cobro_cuenta", f"P{numero}"))
    rel = docs.get(("cobro_relacion", f"P{numero}"))
    salida = []
    for clave, texto, auto in SOPORTES:
        ok, detalle, doc_id = False, "", None
        if clave == "prefactura":
            ok = bool(f["prefactura_aprobada"]); doc_id = cuenta.id if cuenta else None
            detalle = ("Aprobada el " + f["prefactura_aprobada"]) if ok else ("Enviada el " + f["prefactura_enviada"] if f["prefactura_enviada"] else ("Generada, falta enviarla." if cuenta else "Falta generarla."))
        elif clave == "informes":
            ok = not faltan
            detalle = "Todos generados." if ok else "Faltan: " + ", ".join(faltan)
        elif clave == "relacion":
            ok = rel is not None; doc_id = rel.id if rel else None
            detalle = "Generada." if ok else "Falta generarla."
        elif clave == "recibo":
            ok = bool(f["recibo_satisfaccion"])
            detalle = ("Recibido el " + f["recibo_satisfaccion"]) if ok else "Falta la fecha del recibo a satisfacción."
        elif clave == "factura":
            ok = bool(f["factura_numero"])
            detalle = (f"Factura {f['factura_numero']}") if ok else "Falta el número de la factura."
        else:
            ok = bool(manual.get(clave))
            detalle = "Marcado como listo." if ok else "Marque cuando lo tenga."
        salida.append({"clave": clave, "texto": texto, "auto": auto, "ok": ok, "detalle": detalle, "documento": doc_id})
    return salida
