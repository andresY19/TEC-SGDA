"""
Documentos del contrato: se generan con los datos de la plataforma, se editan en pantalla
bloque por bloque y salen en Word, presentación o Excel.

El contenido es una lista de bloques y no un archivo, por tres razones. Se puede editar un
párrafo o una celda sin rehacer el documento. Se guarda en la base, con quién lo editó y
cuándo. Y el mismo contenido sirve para cualquier formato de salida.

    {"t": "h1" | "h2" | "h3", "x": "texto"}
    {"t": "p", "x": "texto"}
    {"t": "li", "items": ["uno", "dos"]}
    {"t": "tabla", "cols": ["A", "B"], "rows": [["1", "2"]]}
    {"t": "slide", "titulo": "…", "puntos": ["…"], "tabla": {"cols": [], "rows": []}}   (presentaciones)

Lo que la plataforma mide queda escrito como dato; lo que solo una persona puede afirmar
queda como texto entre corchetes para que lo complete o lo borre.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from geology.dominio import contrato as ct
from geology.dominio import seguimiento as seg
from geology.dominio.estados import Estado

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
PEND = "[Completar: {}]"

H1, H2, H3, P, LI, TABLA, SLIDE = "h1", "h2", "h3", "p", "li", "tabla", "slide"


def h1(x): return {"t": H1, "x": x}
def h2(x): return {"t": H2, "x": x}
def h3(x): return {"t": H3, "x": x}
def p(x): return {"t": P, "x": x}
def li(*items): return {"t": LI, "items": [str(i) for i in items]}
def tabla(cols, rows): return {"t": TABLA, "cols": [str(c) for c in cols],
                               "rows": [[("" if c is None else str(c)) for c in r] for r in rows]}
def slide(titulo, puntos=None, t=None):
    d = {"t": SLIDE, "titulo": titulo, "puntos": [str(x) for x in (puntos or [])]}
    if t:
        d["tabla"] = {"cols": [str(c) for c in t["cols"]], "rows": [[str(c) for c in r] for r in t["rows"]]}
    return d


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def moneda(v: float) -> str:
    return "$" + f"{round(v):,}".replace(",", ".")


def num(v: float, dec: int = 2) -> str:
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------------------
# Validación de lo que llega del editor
# ---------------------------------------------------------------------------------------
def validar_bloques(contenido: dict) -> dict:
    if not isinstance(contenido, dict) or not isinstance(contenido.get("bloques"), list):
        raise ValueError("El documento debe traer una lista de bloques.")
    limpios = []
    for b in contenido["bloques"][:2000]:
        if not isinstance(b, dict):
            raise ValueError("Un bloque no tiene el formato esperado.")
        t = b.get("t")
        if t in (H1, H2, H3, P):
            limpios.append({"t": t, "x": str(b.get("x", ""))[:20000]})
        elif t == LI:
            limpios.append({"t": LI, "items": [str(i)[:5000] for i in (b.get("items") or [])][:500]})
        elif t == TABLA:
            cols = [str(c)[:300] for c in (b.get("cols") or [])][:40]
            filas = [[str(c)[:5000] for c in (r or [])][:len(cols)] for r in (b.get("rows") or [])][:5000]
            filas = [r + [""] * (len(cols) - len(r)) for r in filas]
            limpios.append({"t": TABLA, "cols": cols, "rows": filas})
        elif t == SLIDE:
            d = {"t": SLIDE, "titulo": str(b.get("titulo", ""))[:300],
                 "puntos": [str(x)[:2000] for x in (b.get("puntos") or [])][:40]}
            tb = b.get("tabla")
            if isinstance(tb, dict) and tb.get("cols"):
                cols = [str(c)[:200] for c in tb["cols"]][:12]
                d["tabla"] = {"cols": cols, "rows": [[str(c)[:1000] for c in (r or [])][:len(cols)]
                                                     for r in (tb.get("rows") or [])][:40]}
            limpios.append(d)
        else:
            raise ValueError(f"Tipo de bloque desconocido: {t!r}.")
    salida = {"bloques": limpios}
    if isinstance(contenido.get("meta"), dict):
        salida["meta"] = {str(k)[:60]: str(v)[:500] for k, v in contenido["meta"].items()}
    return salida


# ---------------------------------------------------------------------------------------
# Salidas: Word, presentación y Excel
# ---------------------------------------------------------------------------------------
def a_docx(titulo: str, contenido: dict, subtitulo: str = "") -> bytes:
    from docx import Document
    from docx.shared import Pt
    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    d.add_heading(titulo, level=0)
    if subtitulo:
        d.add_paragraph(subtitulo)
    for b in contenido.get("bloques", []):
        t = b["t"]
        if t in (H1, H2, H3):
            d.add_heading(b["x"], level={H1: 1, H2: 2, H3: 3}[t])
        elif t == P:
            d.add_paragraph(b["x"])
        elif t == LI:
            for item in b["items"]:
                d.add_paragraph(item, style="List Bullet")
        elif t == TABLA and b["cols"]:
            tb = d.add_table(rows=1, cols=len(b["cols"]))
            tb.style = "Light Grid Accent 1"
            for i, c in enumerate(b["cols"]):
                tb.rows[0].cells[i].text = c
            for r in b["rows"]:
                celdas = tb.add_row().cells
                for i, v in enumerate(r):
                    celdas[i].text = v
            d.add_paragraph("")
        elif t == SLIDE:
            d.add_heading(b["titulo"], level=2)
            for x in b["puntos"]:
                d.add_paragraph(x, style="List Bullet")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def a_pptx(titulo: str, contenido: dict, subtitulo: str = "") -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    pr = Presentation()
    pr.slide_width, pr.slide_height = Inches(13.333), Inches(7.5)
    portada = pr.slides.add_slide(pr.slide_layouts[0])
    portada.shapes.title.text = titulo
    if len(portada.placeholders) > 1:
        portada.placeholders[1].text = subtitulo
    for b in contenido.get("bloques", []):
        if b["t"] != SLIDE:
            continue
        s = pr.slides.add_slide(pr.slide_layouts[5])
        s.shapes.title.text = b["titulo"]
        tope = Inches(1.6)
        if b["puntos"]:
            caja = s.shapes.add_textbox(Inches(0.6), tope, Inches(12.1), Inches(2.6 if b.get("tabla") else 5.2))
            tf = caja.text_frame
            tf.word_wrap = True
            for i, x in enumerate(b["puntos"]):
                para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                para.text = "• " + x
                para.font.size = Pt(18 if not b.get("tabla") else 14)
            tope = Inches(4.3) if b.get("tabla") else tope
        tb = b.get("tabla")
        if tb and tb["cols"]:
            filas = tb["rows"][:12]
            alto = Inches(0.35) * (len(filas) + 1)
            forma = s.shapes.add_table(len(filas) + 1, len(tb["cols"]), Inches(0.6), tope, Inches(12.1), alto)
            t = forma.table
            for i, c in enumerate(tb["cols"]):
                t.cell(0, i).text = c
            for r, fila in enumerate(filas, start=1):
                for i, v in enumerate(fila):
                    t.cell(r, i).text = v
            for fila in t.rows:
                for c in fila.cells:
                    for para in c.text_frame.paragraphs:
                        para.font.size = Pt(11)
    out = io.BytesIO()
    pr.save(out)
    return out.getvalue()


def a_xlsx(titulo: str, contenido: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    n = 0
    antes = titulo
    for b in contenido.get("bloques", []):
        if b["t"] in (H1, H2, H3):
            antes = b["x"]
        if b["t"] != TABLA or not b["cols"]:
            continue
        n += 1
        nombre = "".join(ch for ch in antes if ch not in "[]:*?/\\\\")[:28] or f"Hoja {n}"
        base, k = nombre, 2
        while nombre in wb.sheetnames:
            nombre = f"{base[:25]} {k}"
            k += 1
        ws = wb.create_sheet(nombre)
        ws.append(b["cols"])
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="E8DFCB")
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for r in b["rows"]:
            ws.append(r)
        for i, col in enumerate(b["cols"], start=1):
            ancho = max([len(col)] + [len(r[i - 1]) for r in b["rows"] if len(r) >= i] + [8])
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(60, ancho + 2)
        ws.freeze_panes = "A2"
    if not wb.sheetnames:
        wb.create_sheet("Documento").append([titulo])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------------------
# Datos compartidos por los informes
# ---------------------------------------------------------------------------------------
def produccion_del_periodo(db: Session, desde: date, hasta: date) -> dict:
    from geology.dominio.produccion import LABORES, PRODUCTIVAS
    from geology.modelos import Trazabilidad
    fin = datetime.combine(hasta, datetime.max.time())
    ini = datetime.combine(desde, datetime.min.time())
    filas = (db.query(Trazabilidad.usuario, Trazabilidad.accion, func.count(Trazabilidad.id))
               .filter(Trazabilidad.fecha >= ini, Trazabilidad.fecha <= fin,
                       Trazabilidad.accion.in_(PRODUCTIVAS))
               .group_by(Trazabilidad.usuario, Trazabilidad.accion).all())
    por_persona: dict[str, dict] = {}
    for usuario, accion, n in filas:
        if not usuario:
            continue
        por_persona.setdefault(usuario, {})[accion] = n
    total = sum(sum(v.values()) for v in por_persona.values())
    return {"por_persona": por_persona, "total": total, "labores": LABORES,
            "personas": len(por_persona)}


def calidad_global(db: Session) -> dict:
    from geology.dominio.control_calidad import ERROR, revisar_todo
    inf = revisar_todo(db)
    con_error = {h.carpeta for h in inf.hallazgos if h.gravedad == ERROR}
    return {"revisados": inf.revisados, "carpetas_con_error": len(con_error),
            "porcentaje": round(100 * len(con_error) / inf.revisados, 1) if inf.revisados else 0.0,
            "por_prueba": inf.resumen()["por_prueba"]}


def _firmas(pr: dict) -> dict:
    return tabla(["Presenta, EL CONTRATISTA", "Aprueba, SUPERVISIÓN SGC"],
                 [[pr["representante"], pr["supervisor"]],
                  [f"Representante legal, {pr['contratista']}", "Supervisor del contrato, SGC"],
                  ["Fecha: ____________", "Fecha: ____________"]])


def _encabezado(pr: dict) -> dict:
    return tabla(["Campo", "Detalle"], [
        ["Contrato", f"{pr['contrato_numero']} · {pr['proceso']}"], ["Contratante", pr["contratante"]],
        ["Contratista", f"{pr['contratista']}, NIT {pr['nit']}"],
        ["Supervisor", pr["supervisor"]], ["Valor", moneda(float(pr["valor"])) + " (IVA incluido)"],
        ["Plazo", f"{fecha_larga(date.fromisoformat(pr['fecha_inicio']))} al {fecha_larga(date.fromisoformat(pr['fecha_fin']))}"]])


# ---------------------------------------------------------------------------------------
# Informe mensual (obligación 19) y soporte de cobro
# ---------------------------------------------------------------------------------------
def informe_mensual(db: Session, anio: int, mes: int) -> tuple[str, dict]:
    ct.sembrar(db)
    pr = ct.parametros(db)
    ini = date(anio, mes, 1)
    fin = ct.agregar_meses(ini, 1) - timedelta(days=1)
    contrato_ini = date.fromisoformat(pr["fecha_inicio"])
    desde = max(ini, contrato_ini)
    valor = float(pr["valor"])
    base = float(pr["ml_base"])
    res = ct.resumen(db)
    mes_ml = ct.ml_del_periodo(db, desde, min(fin, date.today()))
    acum = res["ml"]
    prod = produccion_del_periodo(db, desde, fin)
    cal = calidad_global(db)
    lotes = ct._lotes(db)
    lote_vig = ct.lote_de(db, min(fin, date.today()))
    fin_corte = min(fin, date.today())
    plan_corte = ct.plan_a_la_fecha(lotes, fin_corte)
    meta_mes = ct.plan_a_la_fecha(lotes, fin_corte) - ct.plan_a_la_fecha(lotes, desde - timedelta(days=1))
    valor_ml = float(pr["valor_ml"])
    pagados = float(pr["ml_contrato"])
    from geology.modelos import ObligacionContrato, ObservacionSupervision
    obs_mes = (db.query(ObservacionSupervision)
                 .filter(ObservacionSupervision.fecha >= desde, ObservacionSupervision.fecha <= fin).all())
    estados = {o.numero: o for o in db.query(ObligacionContrato).all()}

    persona_dias = max(1, prod["personas"] * ct.dias_habiles(desde, fin_corte))
    b = [h1(f"Informe mensual de ejecución · {MESES[mes - 1].capitalize()} de {anio}"),
         p(f"Contrato {pr['contrato_numero']} · {pr['contratante']}. Documento generado por la plataforma el {fecha_larga(date.today())} con los datos del corte; lo que no puede medirse queda entre corchetes para completar."),
         h2("1. Datos del contrato"), _encabezado(pr),
         h2("2. Periodo reportado"),
         p(f"Del {fecha_larga(desde)} al {fecha_larga(fin_corte)}."
           + (f" Corresponde al {lote_vig.nombre} ({fecha_larga(lote_vig.fecha_inicio)} a {fecha_larga(lote_vig.fecha_fin)}), con meta de {lote_vig.meta_ml:g} ML." if lote_vig else "")),
         h2("3. Avance físico"),
         tabla(["Indicador", "Valor"], [
             ["Metros lineales intervenidos en el mes", num(mes_ml["ml"])],
             ["Meta del plan para el mes", num(meta_mes)],
             ["Metros lineales intervenidos acumulados (equivalentes)", f"{num(acum['ml_equivalentes'])} de {num(base, 0)}"],
             ["Metros lineales completos (cajas con todas sus carpetas)", num(acum["ml_completos"])],
             ["Avance físico acumulado", f"{acum['porcentaje']} %"],
             ["Plan acumulado a la fecha de corte", num(plan_corte)],
             ["Diferencia frente al plan", num(acum["ml_equivalentes"] - plan_corte)],
             ["Carpetas intervenidas", f"{acum['carpetas_intervenidas']} de {acum['carpetas']}"],
             ["Cajas completas", f"{acum['cajas_completas']} de {acum['cajas_en_inventario']}"]]),
         p("Metros lineales calculados a razón de 0,25 ML por caja X-200 (cuatro cajas por metro). «Equivalentes» es proporcional al avance dentro de cada caja; «completos» solo cuenta las cajas con todas sus carpetas intervenidas."),
         h2("4. Personal y producción"),
         p(f"Personas con producción registrada en el periodo: {prod['personas']}. Producción total (verificaciones, descripciones generadas y validadas, aprobaciones y reubicaciones): {prod['total']} acciones."),
         tabla(["Persona", "Hojas verificadas", "Descripciones generadas", "Descripciones validadas", "Aprobadas", "Reubicadas", "Total"],
               [[nom, a.get("verificar", 0), a.get("generar_isadg", 0), a.get("validar_isadg", 0), a.get("aprobar", 0),
                 a.get("reubicar", 0), sum(a.values())] for nom, a in sorted(prod["por_persona"].items(), key=lambda kv: -sum(kv[1].values()))]),
         p(f"Productividad: {num(mes_ml['ml'] / persona_dias, 3)} ML por persona y día hábil (meta del plan: 0,25 ML por técnico y día)."),
         h2("5. Calidad"),
         p(f"Control de calidad automático sobre {cal['revisados']} expedientes cargados: {cal['carpetas_con_error']} con errores, es decir {cal['porcentaje']} % frente al máximo contractual de {pr['error_maximo_pct']} %. Esta medición cubre lo que la plataforma puede comprobar; el muestreo de la supervisión se registra aparte."),
         tabla(["Prueba", "Hallazgos"], [[k, v] for k, v in list(cal["por_prueba"].items())[:15]]) if cal["por_prueba"] else p("Sin hallazgos."),
         h3("Observaciones de la supervisión en el mes"),
         tabla(["Fecha", "Origen", "Descripción", "Límite", "Estado"],
               [[o.fecha.isoformat(), o.origen, o.descripcion[:200], o.fecha_limite.isoformat(), o.estado] for o in obs_mes])
         if obs_mes else p("No se registraron observaciones de la supervisión en el periodo."),
         h2("6. Ejecución presupuestal"),
         tabla(["Concepto", "Valor"], [
             ["Valor del contrato", moneda(valor)],
             ["Valor por metro lineal (IVA incluido)", moneda(valor_ml)],
             ["Valor de los metros lineales completos pagaderos (hasta " + num(pagados, 0) + " ML; el resto es valor agregado sin costo)", moneda(min(acum["ml_completos"], pagados) * valor_ml)],
             ["Facturado a la fecha", moneda(res["finanzas"]["facturado"])],
             ["Avance financiero", f"{res['finanzas']['avance_financiero_pct']} %"]]),
         p("La factura y los soportes de pago (certificación de cumplimiento, recibo a satisfacción y certificación de aportes a seguridad social y parafiscales) se radican según la cláusula cuarta."),
         h2("7. Cumplimiento de obligaciones"),
         tabla(["N.º", "Obligación", "Estado", "Evidencia"],
               [[n, t, estados[n].estado if n in estados else "pendiente", (estados[n].evidencia or "") if n in estados else ""]
                for n, t, _ in ct.OBLIGACIONES]),
         h2("8. Dificultades y acciones correctivas"),
         li(*([a["texto"] for a in res["alertas"]] or [PEND.format("dificultades del periodo")])),
         p(PEND.format("acciones correctivas aplicadas")),
         h2("9. Actividades del próximo mes"),
         li(*[f"{lt.nombre}: meta de {lt.meta_ml:g} ML entre el {fecha_larga(lt.fecha_inicio)} y el {fecha_larga(lt.fecha_fin)}."
              for lt in lotes if lt.fecha_fin >= date.today()][:2]),
         p("Seguimiento del proceso de eliminación documental, base descriptiva ISAD(G), digitalización de las series que lo requieran y cierre de lote con muestreo de la supervisión."),
         _firmas(pr)]
    return f"Informe mensual {MESES[mes - 1]} {anio}", {"bloques": b, "meta": {"mes": f"{anio}-{mes:02d}"}}


# ---------------------------------------------------------------------------------------
# Informe de lote y cuenta de cobro
# ---------------------------------------------------------------------------------------
def informe_de_lote(db: Session, numero: int) -> tuple[str, dict]:
    ct.sembrar(db)
    pr = ct.parametros(db)
    from geology.modelos import LoteContrato
    lt = db.query(LoteContrato).filter(LoteContrato.numero == numero).first()
    if not lt:
        raise ValueError(f"No existe el lote {numero}.")
    valor = float(pr["valor"])
    base = float(pr["ml_base"])
    hasta = min(lt.fecha_fin, date.today())
    r = ct.ml_del_periodo(db, lt.fecha_inicio, hasta)
    cal = calidad_global(db)
    valor_ml = float(pr["valor_ml"])
    pagados = float(pr["ml_contrato"])
    cobrable = min(r["ml_completos"], pagados) * valor_ml
    b = [h1(f"Informe de avance y soporte de cobro · {lt.nombre}"),
         p(f"Corte por lote para recibo a satisfacción y pago. Generado el {fecha_larga(date.today())}."),
         h2("1. Datos del contrato"), _encabezado(pr),
         h2("2. Lote"),
         tabla(["Campo", "Valor"], [
             ["Lote", lt.nombre], ["Periodo", f"{fecha_larga(lt.fecha_inicio)} a {fecha_larga(lt.fecha_fin)}"],
             ["Meta del lote", f"{lt.meta_ml:g} ML"],
             ["Metros lineales intervenidos en el lote (equivalentes)", num(r["ml"])],
             ["Metros lineales completos en el lote (cajas cerradas)", num(r["ml_completos"])],
             ["Carpetas intervenidas en el lote", r["carpetas"]],
             ["Cumplimiento de la meta", f"{round(100 * r['ml'] / lt.meta_ml, 1) if lt.meta_ml else 0} %"]]),
         h2("3. Calidad"),
         p(f"Control automático: {cal['carpetas_con_error']} de {cal['revisados']} expedientes con error ({cal['porcentaje']} %); máximo contractual {pr['error_maximo_pct']} %. Muestreo de la supervisión: {PEND.format('resultado de la muestra y número de expedientes revisados')}"),
         h2("4. Valor a facturar (estimado)"),
         tabla(["Concepto", "Valor"], [
             ["Valor por metro lineal", moneda(valor_ml)],
             ["Metros lineales completos del lote", num(r["ml_completos"])],
             ["Valor del lote, IVA incluido", moneda(cobrable)],
             ["Ya facturado en este lote", moneda(lt.valor_facturado or 0)]]),
         p("Valor calculado con la base de pago configurada (metros lineales a intervenir). Si la supervisión confirma otra base, ajústela en los parámetros del contrato; el valor definitivo lo establece el recibo a satisfacción."),
         h2("5. Soportes que se anexan a la factura"),
         li("Factura electrónica validada por la DIAN.", "Certificación de cumplimiento y recibo a satisfacción del supervisor.",
            "Certificación del revisor fiscal o del representante legal sobre aportes a salud, pensiones, riesgos laborales y parafiscales (artículo 50 de la Ley 789 de 2002).",
            "Acta de recibo del lote.", "FUID del lote y fichas técnicas del lote."),
         _firmas(pr)]
    return f"Informe de lote {numero}", {"bloques": b, "meta": {"lote": str(numero)}}


# ---------------------------------------------------------------------------------------
# Fichas técnicas (obligación 4)
# ---------------------------------------------------------------------------------------
ACTIVIDADES = {
    "IDE": ("Identificación", "Reconocer el productor, la serie y el periodo de cada unidad documental a partir del inventario, la CCD y las TVD.",
            ["Revisar el inventario de origen y el rótulo de la carpeta.", "Identificar productor, oficina y periodo institucional.", "Cotejar con la TVD convalidada.", "Registrar diferencias en el FUID."]),
    "CLA": ("Clasificación", "Estructurar las unidades documentales por procedencia en fondo, sección, subsección, periodo, serie y subserie según las TVD.",
            ["Asignar el periodo según las fechas del expediente.", "Ubicar la subserie de la TVD del periodo.", "Validar la clasificación con la persona revisora.", "Dejar la clasificación en la hoja de control."]),
    "DEP": ("Depuración", "Retirar de los expedientes duplicados, hojas en blanco, formatos sin diligenciar y documentos de apoyo, dejando constancia.",
            ["Identificar duplicados, blancos y formatos sin diligenciar.", "Separar los documentos de apoyo.", "Registrar lo retirado en el inventario de apoyo y duplicados.", "Verificar con el criterio de las TVD."]),
    "ORD": ("Ordenación", "Disponer el orden interno de cada expediente respetando el orden original.",
            ["Establecer el criterio de orden (cronológico, alfabético o temático).", "Ordenar sin desempastar los tomos.", "Verificar la secuencia.", "Registrar los trámites en la hoja de control."]),
    "FOL": ("Foliación", "Garantizar la integridad del expediente con una foliación consecutiva conforme al instructivo del Archivo General de la Nación.",
            ["Foliar en la esquina superior derecha, consecutivamente.", "Verificar los folios contra el inventario.", "Registrar diferencias en la hoja de control y el FUID.", "Autocontrol por muestreo."]),
    "DES": ("Descripción", "Describir las unidades documentales con la norma ISAD(G) y la NTC 4095 para la transferencia secundaria.",
            ["Diligenciar la hoja de control con los trámites.", "Elaborar los elementos de descripción de la unidad.", "Revisar y validar la descripción.", "Aprobar y archivar la ficha."]),
    "INV": ("Inventario", "Elaborar el Formato Único de Inventario Documental de lo intervenido, por periodo y disposición final.",
            ["Asignar caja definitiva por periodo.", "Registrar carpetas, folios y ubicación en el FUID.", "Marcar derechos humanos, niveles de acceso y novedades.", "Cerrar la caja y rotular."]),
    "VAL": ("Valoración", "Aplicar la valoración documental de la TVD convalidada a cada subserie.",
            ["Identificar la disposición final de la subserie.", "Documentar la retención y el procedimiento.", "Registrar la valoración en la descripción.", "Reportar casos dudosos a la dirección."]),
    "DIS": ("Disposición final", "Aplicar la disposición final (conservación total, selección o eliminación) y preparar la sustentación ante el Comité.",
            ["Separar lo de eliminación y selección.", "Elaborar el FUID de eliminación.", "Elaborar el informe y la presentación para el Comité.", "Sustentar y esperar el aval."]),
}


def ficha_tecnica(db: Session, actividad: str, numero_lote: int) -> tuple[str, dict]:
    ct.sembrar(db)
    pr = ct.parametros(db)
    from geology.modelos import LoteContrato
    lt = db.query(LoteContrato).filter(LoteContrato.numero == numero_lote).first()
    if not lt or actividad not in ACTIVIDADES:
        raise ValueError("Lote o actividad desconocidos.")
    nombre, objetivo, pasos = ACTIVIDADES[actividad]
    hasta = min(lt.fecha_fin, date.today())
    r = ct.ml_del_periodo(db, lt.fecha_inicio, hasta)
    prod = produccion_del_periodo(db, lt.fecha_inicio, hasta)
    cal = calidad_global(db)
    codigo = f"FT-733-{actividad}-L{numero_lote}"
    filas = [
        ["Código de la ficha", f"{codigo}-v1"],
        ["Nombre de la actividad", nombre],
        ["Lote y periodo de ejecución", f"{lt.nombre}, del {fecha_larga(lt.fecha_inicio)} al {fecha_larga(lt.fecha_fin)}. Acta de recibo: {PEND.format('número y fecha del acta')}"],
        ["Objetivo de la actividad", objetivo],
        ["Alcance", f"Metros lineales intervenidos en el lote: {num(r['ml'])} ML (meta {lt.meta_ml:g} ML); {r['carpetas']} carpetas."],
        ["Base normativa", "Ley 594 de 2000; Acuerdo 001 de 2024 del Archivo General de la Nación; NTC 4095:2013; Instructivo de foliación del AGN; Tablas de Valoración Documental convalidadas."],
        ["Procedimiento metodológico", " ".join(f"{i}) {x}" for i, x in enumerate(pasos, start=1))],
        ["Técnicas archivísticas", "Principio de procedencia y orden original; descripción multinivel ISAD(G)."],
        ["Recursos humanos", f"{prod['personas']} personas con producción registrada en el lote. Ejecuta el personal técnico; revisa el Profesional en Ciencias de la Información."],
        ["Recursos tecnológicos", "Plataforma Geology (hoja de control, descripción, control de calidad y seguimiento), estaciones de trabajo, escáneres."],
        ["Recursos físicos", "Mesas de trabajo, área de primeros auxilios documentales, iluminación adecuada, cajas X-100 y X-200."],
        ["Herramientas e instrumentos", "TVD, Cuadro de Clasificación Documental, FUID (F-GDM-003), hoja de control (F-GDM-007), rótulos (F-GDM-006 y F-GDM-008)."],
        ["Insumos de entrada", "Documentación e inventarios en estado natural recibidos del Servicio Geológico Colombiano."],
        ["Productos o entregables", "Expedientes intervenidos, hoja de control, FUID, rótulos y descripción ISAD(G) según la actividad."],
        ["Criterios técnicos de aceptación", f"Error por lote de {pr['error_maximo_pct']} % o menos; coherencia entre ficha, FUID y base ISAD(G)."],
        ["Controles de calidad", "Autocontrol por muestreo del profesional y verificación de la supervisión; control de calidad automático de la plataforma."],
        ["Riesgos asociados", "R1, R2, R3, R6, R10, R18 y R23 de la matriz de riesgos del plan de trabajo."],
        ["Evidencias generadas", "Registro de la bitácora de la plataforma, registro fotográfico, lista de verificación de cierre de lote."],
        ["Registros documentales", f"{codigo}; FUID; hoja de control; base ISAD(G)."],
        ["Responsable de ejecución", "Técnico o tecnólogo asignado."],
        ["Responsable de revisión", "Profesional en Ciencias de la Información."],
        ["Responsable de aprobación", f"Gerente de proyecto (validación de la supervisión: {pr['supervisor']})."],
        ["Tiempo estimado de ejecución", PEND.format("horas por expediente")],
        ["Indicadores de cumplimiento", f"Carpetas con error: {cal['carpetas_con_error']} de {cal['revisados']} ({cal['porcentaje']} %). Meta del lote cumplida en {round(100 * r['ml'] / lt.meta_ml, 1) if lt.meta_ml else 0} %."],
        ["Observaciones técnicas", PEND.format("novedades, soportes especiales, información de derechos humanos")],
    ]
    b = [h1(f"Ficha técnica {codigo}"), p(f"{pr['contrato_numero']} · {pr['contratante']}"),
         tabla(["Campo", "Valor diligenciado"], filas), _firmas(pr)]
    return f"Ficha técnica {codigo}", {"bloques": b, "meta": {"actividad": actividad, "lote": str(numero_lote)}}


# ---------------------------------------------------------------------------------------
# Informe técnico final (obligación 13)
# ---------------------------------------------------------------------------------------
def informe_final(db: Session) -> tuple[str, dict]:
    ct.sembrar(db)
    pr = ct.parametros(db)
    res = ct.resumen(db)
    cal = calidad_global(db)
    from geology.modelos import (Expediente, ItemEliminacion, ObligacionContrato, ObservacionSupervision,
                                 Periodo, ProcesoEliminacion, UnidadInventario)
    from geology.dominio.produccion import _embudo
    _, emb = _embudo(db)
    por_periodo = (db.query(UnidadInventario.periodo, func.count(UnidadInventario.id),
                            func.coalesce(func.sum(UnidadInventario.folios), 0))
                     .group_by(UnidadInventario.periodo).order_by(UnidadInventario.periodo).all())
    obs = db.query(ObservacionSupervision).all()
    procesos = db.query(ProcesoEliminacion).order_by(ProcesoEliminacion.id).all()
    estados = {o.numero: o for o in db.query(ObligacionContrato).all()}

    b = [h1("Informe técnico final"),
         p(f"Contrato {pr['contrato_numero']} · {pr['contratante']}. Generado el {fecha_larga(date.today())}."),
         h2("1. Datos del contrato"), _encabezado(pr),
         h2("2. Resultados cuantitativos"),
         tabla(["Indicador", "Resultado"], [
             ["Metros lineales intervenidos", f"{num(res['ml']['ml_equivalentes'])} de {num(float(pr['ml_base']), 0)} ({res['ml']['porcentaje']} %)"],
             ["Cajas completas", f"{res['ml']['cajas_completas']} de {res['ml']['cajas_en_inventario']}"],
             ["Carpetas inventariadas", emb["inventariadas"]], ["Carpetas con hoja de control", emb["con_hoja_de_control"]],
             ["Carpetas con descripción", emb["descritas"]], ["Descripciones validadas", emb["validadas"]],
             ["Descripciones aprobadas y archivadas", emb["archivadas"]], ["Carpetas en caja definitiva", emb["en_caja_definitiva"]],
             ["Folios registrados", emb["folios_registrados"]]]),
         h3("Inventario de origen por periodo"),
         tabla(["Periodo", "Carpetas", "Folios"], [[a or "Sin periodo", b_, f] for a, b_, f in por_periodo]),
         h2("3. Procesos de organización"),
         p("Se aplicaron la identificación, clasificación, depuración, ordenación, foliación, descripción, inventario, valoración y disposición final conforme a las TVD convalidadas, con una ficha técnica por actividad y por lote."),
         tabla(["Lote", "Meta ML", "Periodo", "Recibido a satisfacción", "Facturado"],
               [[l["nombre"], l["meta_ml"], f"{l['inicio']} a {l['fin']}", l["recibido_en"] or "—", l["facturado_en"] or "—"] for l in res["lotes"]]),
         h2("4. Valoración y selección"),
         p(PEND.format("síntesis cualitativa de la valoración: criterios aplicados, series de selección y muestra elegida")),
         h2("5. Eliminación documental"),
         (tabla(["Propuesta", "Estado", "Acta del Comité", "Fecha de aprobación", "Publicación desde"],
                [[x.nombre, x.estado, x.acta_comite or "—", x.fecha_aprobacion.isoformat() if x.fecha_aprobacion else "—",
                  x.publicacion_inicio.isoformat() if x.publicacion_inicio else "—"] for x in procesos])
          if procesos else p("No se creó ninguna propuesta de eliminación en la plataforma.")),
         p("Conforme al procedimiento de eliminación documental, la aprobación del Comité Institucional de Gestión y Desempeño, la publicación del inventario por sesenta días hábiles, el eventual concepto técnico del Archivo General de la Nación, la eliminación física, la firma y la publicación del acta corresponden al Servicio Geológico Colombiano. El alcance de este contrato cierra con la entrega del FUID de eliminación, el informe técnico, la presentación y la sustentación ante el Comité."),
         h2("6. Transferencia documental"),
         p("La base descriptiva ISAD(G) de los expedientes de conservación total y de la muestra de selección queda lista para la transferencia secundaria. " + PEND.format("fecha y acta de entrega de la base")),
         h2("7. Calidad y observaciones de la supervisión"),
         p(f"Control automático: {cal['carpetas_con_error']} de {cal['revisados']} expedientes con error ({cal['porcentaje']} %). Observaciones de la supervisión: {len(obs)}; atendidas: {sum(1 for o in obs if o.estado != 'abierta')}."),
         h2("8. Obligaciones contractuales"),
         tabla(["N.º", "Obligación", "Estado", "Evidencia"],
               [[n, t, estados[n].estado if n in estados else "pendiente", (estados[n].evidencia or "") if n in estados else ""]
                for n, t, _ in ct.OBLIGACIONES]),
         h2("9. Retorno y cierre"),
         p(PEND.format("acta de retorno de las cajas al archivo central, acta de recibo final y estado de la liquidación")),
         h2("10. Conclusiones y recomendaciones"),
         p(PEND.format("conclusiones")), _firmas(pr)]
    return "Informe técnico final", {"bloques": b, "meta": {}}
