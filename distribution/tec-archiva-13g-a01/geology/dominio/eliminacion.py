"""
Eliminación documental según el procedimiento PR-GDM-001 versión 3 del Servicio Geológico
(que el cambio de versión re-codificó como PR-SAD-PED-001) y el artículo 4.5.4 del Acuerdo 001
de 2024 del Archivo General de la Nación.

Qué le toca a cada parte. Al contratista le toca proponer el inventario, elaborar el informe y
la presentación y sustentarlos ante el Comité Institucional de Gestión y Desempeño. Al Servicio
Geológico le tocan la aprobación del Comité, la publicación del inventario por sesenta días
hábiles, el eventual concepto técnico del Archivo General de la Nación, la eliminación física,
la firma del acta y su publicación. La plataforma sigue las dos partes para que se vea en qué va
cada paso y cuándo vence cada plazo.

Reglas que este módulo hace cumplir:
  - Nada se elimina por una decisión automática. La plataforma PROPONE candidatas y una persona
    confirma o excluye cada una; solo lo confirmado entra a los documentos.
  - Lo que el asunto sugiere que contiene información de derechos humanos no se puede confirmar
    en lote y queda señalado para una decisión consciente.
  - Digitalizar nunca es motivo para eliminar el original físico.
  - La eliminación es por series y subseries, y el acta lleva series, fechas extremas, volumen,
    método y los datos de aprobación y convalidación de las TVD.
El estado del proceso se calcula con las fechas registradas; no se guarda aparte.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from geology.dominio import contrato as ct
from geology.dominio import disposicion as disp
from geology.dominio import documentos as doc
from geology.dominio.documentos import (PEND, fecha_larga, h1, h2, h3, li, num, p, slide, tabla)

ESTADOS = [
    ("propuesta", "Propuesta en elaboración"), ("informe_listo", "Informe y presentación listos"),
    ("sustentada", "Sustentada ante el Comité"), ("aprobada", "Aprobada por el Comité"),
    ("publicada", "Publicada para observaciones"), ("concepto_agn", "En concepto del Archivo General de la Nación"),
    ("eliminada", "Eliminada"), ("acta_publicada", "Acta publicada"),
]
DIAS_PUBLICACION = 60
DIAS_CONCEPTO = 30
FOLIOS_POR_ML = 4800    # 1.200 folios por caja X-200 y cuatro cajas por metro lineal

_DDHH = re.compile(r"derechos humanos|desaparici|masacre|v[ií]ctima|conflicto armado|secuestr|tortura|"
                   r"desplazamiento forzado|violaci[oó]n", re.I)


def posible_ddhh(texto: str) -> bool:
    return bool(_DDHH.search(texto or ""))


# ---------------------------------------------------------------------------------------
# Proceso y estado
# ---------------------------------------------------------------------------------------
def estado_de(db: Session, pr) -> str:
    from geology.modelos import DocumentoContrato
    if pr.acta_publicada:
        return "acta_publicada"
    if pr.fecha_eliminacion:
        return "eliminada"
    if pr.hubo_observaciones and pr.concepto_solicitado and not pr.concepto_recibido:
        return "concepto_agn"
    if pr.publicacion_inicio:
        return "publicada"
    if pr.fecha_aprobacion:
        return "aprobada"
    if pr.fecha_sustentacion:
        return "sustentada"
    tipos = {t for (t,) in db.query(DocumentoContrato.tipo).filter(DocumentoContrato.proceso_id == pr.id).all()}
    if {"elim_informe", "elim_presentacion"} <= tipos:
        return "informe_listo"
    return "propuesta"


def plazos(pr) -> dict:
    """Fechas que se desprenden de lo registrado, en días hábiles."""
    d: dict = {}
    if pr.publicacion_inicio:
        d["publicacion_fin"] = ct.sumar_habiles(pr.publicacion_inicio, DIAS_PUBLICACION).isoformat()
        d["publicacion_vence_despues_del_contrato"] = d["publicacion_fin"] > "2026-12-31"
    elif pr.fecha_aprobacion:
        d["publicacion_fin_si_inicia_al_aprobar"] = ct.sumar_habiles(pr.fecha_aprobacion, DIAS_PUBLICACION).isoformat()
    if pr.concepto_solicitado:
        d["concepto_limite"] = ct.sumar_habiles(pr.concepto_solicitado, DIAS_CONCEPTO).isoformat()
    return d


# ---------------------------------------------------------------------------------------
# Candidatas
# ---------------------------------------------------------------------------------------
def proponer(db: Session, proceso_id: int) -> dict:
    """
    Recorre el inventario de origen, deja como candidatas las carpetas que se parecen a una
    subserie de eliminación o de selección y las anota como «propuesta». No confirma nada.
    """
    from geology.modelos import ItemEliminacion
    candidatas, resumen = disp.revisar_todo(db)
    existentes = {c for (c,) in db.query(ItemEliminacion.codigo_carpeta)
                  .filter(ItemEliminacion.proceso_id == proceso_id).all()}
    nuevas = 0
    for c in candidatas:
        if c.codigo_carpeta in existentes:
            continue
        db.add(ItemEliminacion(
            proceso_id=proceso_id, codigo_carpeta=c.codigo_carpeta, disposicion=c.disposicion,
            periodo=c.periodo, serie_tvd=c.serie_tvd, subserie_tvd=c.subserie_tvd, estado="propuesta",
            motivo=f"Se parece a la subserie «{c.subserie_tvd}» ({c.confianza}, puntaje {c.puntaje}; "
                   f"coinciden: {', '.join(c.coincidencias[:8])}).",
            posible_ddhh=posible_ddhh(c.asunto)))
        nuevas += 1
    db.flush()
    return {"candidatas": len(candidatas), "nuevas": nuevas, "resumen": resumen}


def items_con_datos(db: Session, proceso_id: int, estado: str | None = None) -> list[dict]:
    from geology.modelos import ItemEliminacion, UnidadInventario
    q = (db.query(ItemEliminacion, UnidadInventario)
           .outerjoin(UnidadInventario, UnidadInventario.codigo_carpeta == ItemEliminacion.codigo_carpeta)
           .filter(ItemEliminacion.proceso_id == proceso_id))
    if estado:
        q = q.filter(ItemEliminacion.estado == estado)
    salida = []
    for it, u in q.order_by(ItemEliminacion.periodo, ItemEliminacion.codigo_carpeta).all():
        salida.append({
            "id": it.id, "carpeta": it.codigo_carpeta, "disposicion": it.disposicion, "estado": it.estado,
            "periodo": it.periodo or (u.periodo if u else ""), "serie": it.serie_tvd or "", "subserie": it.subserie_tvd or "",
            "asunto": (u.asunto or "") if u else "", "folios": (u.folios or 0) if u else 0,
            "caja": (u.caja_origen or "") if u else "", "fecha_inicial": u.fecha_inicial.isoformat() if u and u.fecha_inicial else "",
            "fecha_final": u.fecha_final.isoformat() if u and u.fecha_final else "",
            "cod_serie": (u.cod_subserie or u.cod_serie or "") if u else "",
            "motivo": it.motivo or "", "posible_ddhh": it.posible_ddhh, "decidido_por": it.decidido_por})
    return salida


def decidir(db: Session, proceso_id: int, ids: list[int], estado: str, motivo: str, quien: str) -> dict:
    from datetime import datetime
    from geology.modelos import ItemEliminacion
    if estado not in ("propuesta", "confirmada", "excluida"):
        raise ValueError("El estado es propuesta, confirmada o excluida.")
    hechos, bloqueados = 0, []
    for it in db.query(ItemEliminacion).filter(ItemEliminacion.proceso_id == proceso_id,
                                               ItemEliminacion.id.in_(ids)).all():
        if estado == "confirmada" and it.posible_ddhh and len(ids) > 1:
            bloqueados.append(it.codigo_carpeta)
            continue
        it.estado, it.decidido_por, it.decidido_en = estado, quien, datetime.now()
        if motivo:
            it.motivo = ((it.motivo or "") + f" Decisión: {motivo}").strip()
        hechos += 1
    db.flush()
    return {"actualizadas": hechos, "bloqueadas_por_derechos_humanos": bloqueados}


# ---------------------------------------------------------------------------------------
# Agrupación para los documentos
# ---------------------------------------------------------------------------------------
def agrupar(db: Session, proceso_id: int) -> tuple[list[dict], dict]:
    """Lo confirmado, por periodo, serie y subserie: carpetas, folios, fechas extremas y volumen."""
    grupos: dict[tuple, dict] = defaultdict(lambda: {"carpetas": 0, "folios": 0, "cajas": set(), "ini": "", "fin": ""})
    for it in items_con_datos(db, proceso_id, "confirmada"):
        g = grupos[(it["periodo"], it["serie"], it["subserie"], it["disposicion"])]
        g["carpetas"] += 1
        g["folios"] += it["folios"]
        if it["caja"]:
            g["cajas"].add(it["caja"])
        if it["fecha_inicial"] and (not g["ini"] or it["fecha_inicial"] < g["ini"]):
            g["ini"] = it["fecha_inicial"]
        if it["fecha_final"] and it["fecha_final"] > g["fin"]:
            g["fin"] = it["fecha_final"]
    filas = []
    for (periodo, serie, sub, dis), g in sorted(grupos.items()):
        filas.append({"periodo": periodo, "serie": serie, "subserie": sub, "disposicion": dis,
                      "carpetas": g["carpetas"], "folios": g["folios"], "cajas": len(g["cajas"]),
                      "ml": round(g["folios"] / FOLIOS_POR_ML, 2), "ini": g["ini"] or "S/F", "fin": g["fin"] or "S/F"})
    tot = {"carpetas": sum(f["carpetas"] for f in filas), "folios": sum(f["folios"] for f in filas),
           "ml": round(sum(f["ml"] for f in filas), 2), "series": len({(f["serie"], f["subserie"]) for f in filas}),
           "periodos": sorted({f["periodo"] for f in filas if f["periodo"]})}
    return filas, tot


def lista_de_comprobacion(db: Session, pr) -> list[dict]:
    """Los requisitos del numeral 4.1 del procedimiento y en qué van."""
    from geology.modelos import DocumentoContrato, ItemEliminacion, Periodo
    hoy = date.today()
    items = db.query(ItemEliminacion).filter(ItemEliminacion.proceso_id == pr.id).all()
    conf = [i for i in items if i.estado == "confirmada"]
    por_decidir = [i for i in items if i.estado == "propuesta"]
    ddhh = [i for i in conf if i.posible_ddhh]
    periodos = {i.periodo for i in conf if i.periodo}
    sin_conval = [r for r in periodos if not (db.query(Periodo.fecha_convalidacion_tvd)
                                              .filter(Periodo.numero_romano == r).scalar())]
    docs = {t for (t,) in db.query(DocumentoContrato.tipo).filter(DocumentoContrato.proceso_id == pr.id).all()}
    L: list[dict] = []

    def add(texto, ok, detalle="", bloquea=False):
        L.append({"n": len(L) + 1, "texto": texto, "estado": "ok" if ok else ("bloquea" if bloquea else "pendiente"), "detalle": detalle})

    add("Las TVD están aprobadas, convalidadas e inscritas en el Registro Único de Series Documentales",
        bool(conf) and not sin_conval, "Falta la fecha de convalidación en: " + ", ".join(sin_conval) if sin_conval
        else "Confirme además la inscripción en el RUSD." if conf else "Aún no hay carpetas confirmadas.")
    add("Todo está decidido: ninguna carpeta queda como «propuesta»", not por_decidir,
        f"{len(por_decidir)} carpetas sin decidir." if por_decidir else "", bloquea=True)
    por_series = bool(conf) and all(i.serie_tvd and i.subserie_tvd for i in conf)
    add("La eliminación es por series y subseries", por_series,
        "" if por_series else ("Hay carpetas sin serie o subserie de la TVD." if conf else "Aún no hay carpetas confirmadas."))
    add("Las carpetas con posible información de derechos humanos tienen decisión consciente",
        not ddhh, f"{len(ddhh)} confirmadas con ese indicador: revise cada una." if ddhh else "", bloquea=bool(ddhh))
    add("Informe técnico elaborado", "elim_informe" in docs)
    add("Presentación para el Comité elaborada", "elim_presentacion" in docs)
    add("FUID de eliminación elaborado", "elim_fuid" in docs)
    add("Método de eliminación definido para el acta", bool(pr.metodo))
    add("Sustentación ante el Comité Institucional de Gestión y Desempeño", bool(pr.fecha_sustentacion),
        f"Sustentada el {pr.fecha_sustentacion}." if pr.fecha_sustentacion else "")
    add("Aprobación del Comité (acta y fecha)", bool(pr.acta_comite and pr.fecha_aprobacion),
        f"Acta {pr.acta_comite or 'sin número registrado'}, {pr.fecha_aprobacion}." if pr.fecha_aprobacion else "")
    if pr.publicacion_inicio:
        fin = ct.sumar_habiles(pr.publicacion_inicio, DIAS_PUBLICACION)
        add(f"Publicación del inventario por {DIAS_PUBLICACION} días hábiles", hoy >= fin,
            f"Desde el {pr.publicacion_inicio} hasta el {fin} (cuenta aproximada, con festivos de Colombia).")
    else:
        add(f"Publicación del inventario por {DIAS_PUBLICACION} días hábiles", False, "Sin fecha de inicio. La hace el Servicio Geológico.")
    if pr.hubo_observaciones:
        add(f"Concepto técnico del Archivo General de la Nación dentro de {DIAS_CONCEPTO} días hábiles", bool(pr.concepto_recibido),
            f"Solicitado el {pr.concepto_solicitado}." if pr.concepto_solicitado else "Hubo observaciones ciudadanas: falta solicitarlo.")
    else:
        add("Observaciones ciudadanas revisadas", pr.hubo_observaciones is False,
            "Sin registro todavía." if pr.hubo_observaciones is None else "No hubo observaciones.")
    add("Eliminación realizada y acta firmada por la presidencia y la secretaría técnica del Comité", bool(pr.fecha_eliminacion))
    add("Acta de eliminación e inventarios conservados y publicados", bool(pr.acta_publicada))
    return L


# ---------------------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------------------
FUID_COLUMNAS = ["Orden", "Código", "Serie / subserie", "Unidad documental", "Fecha inicial", "Fecha final",
                 "Soporte físico", "Soporte electrónico", "Caja", "Carpeta", "Correlativo", "Folios",
                 "Otro soporte", "Cantidad otro", "Ubicación", "Cant. electrónicos", "Tamaño electrónicos",
                 "DD.HH.", "Público", "Público clasificado", "Reservado", "Notas"]
FUID_CLAVES = ["orden", "codigo", "serie_subserie", "unidad_documental", "fecha_inicial", "fecha_final",
               "soporte_fisico", "soporte_electronico", "caja", "carpeta", "correlativo", "folios",
               "tipo_otro", "cantidad_otro", "ubicacion", "cant_electronicos", "tamano_electronicos",
               "ddhh", "publico", "publico_clasificado", "reservado", "notas"]


def fuid_eliminacion(db: Session, pr) -> tuple[str, dict]:
    filas = []
    for i, it in enumerate(items_con_datos(db, pr.id, "confirmada"), start=1):
        fila = {c: "" for c in FUID_CLAVES}
        fila.update({"orden": i, "codigo": it["cod_serie"], "serie_subserie": " / ".join(x for x in (it["serie"], it["subserie"]) if x),
                     "unidad_documental": it["asunto"], "fecha_inicial": it["fecha_inicial"] or "S/F", "fecha_final": it["fecha_final"],
                     "soporte_fisico": "X", "caja": it["caja"], "correlativo": it["carpeta"], "folios": it["folios"],
                     "ddhh": "X" if it["posible_ddhh"] else "", "publico": "X",
                     "notas": ("Selección: no elegida como muestra. " if it["disposicion"] == "S" else "") + "Propuesta de eliminación."})
        filas.append([str(fila[c]) for c in FUID_CLAVES])
    b = [h1("FUID de la propuesta de eliminación"),
         p(f"Inventario documental de la propuesta «{pr.nombre}», en la estructura del formato F-GDM-003 versión 9. Objeto del inventario: Propuesta de eliminación documental. Generado el {fecha_larga(date.today())}."),
         tabla(FUID_COLUMNAS, filas)]
    return f"FUID de eliminación · {pr.nombre}", {"bloques": b, "meta": {"proceso": str(pr.id)}}


def fuid_a_xlsx_oficial(contenido: dict, pr) -> bytes:
    """El FUID de eliminación (con las ediciones que se le hayan hecho) en la plantilla oficial."""
    from geology.dominio import formatos_sgc as fmt
    tablas = [b for b in contenido.get("bloques", []) if b["t"] == "tabla"]
    if not tablas:
        raise ValueError("El documento no tiene la tabla del FUID.")
    filas = []
    for r in tablas[0]["rows"]:
        d = {k: r[i] for i, k in enumerate(FUID_CLAVES) if i < len(r) and r[i] not in ("", None)}
        if "folios" in d:
            try:
                d["folios"] = int(d["folios"])
            except ValueError:
                pass
        filas.append(d)
    return fmt.fuid(filas, {"entidad_remitente": "Hometic SAS", "entidad_productora": "Servicio Geológico Colombiano",
                            "unidad_administrativa": "", "oficina_productora": "",
                            "objeto": "Documentos para eliminación"})


def _tabla_series(grupos: list[dict]) -> dict:
    return tabla(["Periodo", "Serie", "Subserie", "Disposición", "Carpetas", "Folios", "Cajas", "ML estimados", "Fecha inicial", "Fecha final"],
                 [[g["periodo"], g["serie"], g["subserie"], g["disposicion"], g["carpetas"], g["folios"], g["cajas"], num(g["ml"]), g["ini"], g["fin"]] for g in grupos])


def informe_eliminacion(db: Session, pr) -> tuple[str, dict]:
    pa = ct.parametros(db)
    grupos, tot = agrupar(db, pr.id)
    from geology.modelos import Periodo
    conval = [[r, (db.query(Periodo.fecha_convalidacion_tvd).filter(Periodo.numero_romano == r).scalar() or PEND.format("fecha de convalidación"))]
              for r in tot["periodos"]]
    b = [h1(f"Informe técnico de la propuesta de eliminación · {pr.nombre}"),
         p(f"Contrato {pa['contrato_numero']} · {pa['contratante']}. Elaborado el {fecha_larga(date.today())} para sustentación ante el Comité Institucional de Gestión y Desempeño."),
         h2("1. Objeto y alcance"),
         p("Presentar al Comité la propuesta de eliminación de las series y subseries cuya disposición final es la eliminación, y de la parte de las series de selección que no fue elegida como muestra, conforme a las Tablas de Valoración Documental convalidadas."),
         h2("2. Marco normativo"),
         li("Ley 594 de 2000, Ley General de Archivos.", "Decreto 1080 de 2015.",
            "Acuerdo 001 de 2024 del Archivo General de la Nación, artículo 4.5.4: la eliminación debe estar definida en las TVD o TRD, sustentarse en la valoración documental y aprobarse por el Comité Institucional de Gestión y Desempeño.",
            "Procedimiento de eliminación documental del Servicio Geológico Colombiano, PR-GDM-001 versión 3 (PR-SAD-PED-001)."),
         h2("3. Metodología"),
         p("La plataforma cruzó el asunto de cada carpeta del inventario de origen con las subseries de eliminación y de selección de la TVD del periodo y propuso las coincidentes. El inventario de origen no es de fiar para la clasificación, por lo que cada carpeta fue verificada por una persona del equipo antes de confirmarse. Solo las carpetas confirmadas forman parte de esta propuesta."),
         h2("4. Resultados"),
         tabla(["Concepto", "Valor"], [["Series y subseries", tot["series"]], ["Carpetas", tot["carpetas"]], ["Folios", tot["folios"]],
                                       ["Metros lineales estimados", num(tot["ml"])], ["Periodos", ", ".join(tot["periodos"]) or "—"]]),
         p(f"Los metros lineales se estiman a razón de {FOLIOS_POR_ML:,} folios por metro lineal (1.200 folios por caja X-200, cuatro cajas por metro)".replace(",", ".") + "; el volumen físico exacto se confirma con las cajas."),
         _tabla_series(grupos) if grupos else p("Aún no hay carpetas confirmadas."),
         h2("5. Convalidación de las TVD"),
         tabla(["Periodo", "Fecha de convalidación"], conval) if conval else p(PEND.format("periodos")),
         p(PEND.format("acto de convalidación y número de inscripción en el Registro Único de Series Documentales")),
         h2("6. Exclusiones y salvaguardas"),
         li("No se incluyó ninguna carpeta cuya disposición final esté por definir.",
            "Las carpetas con posible información de derechos humanos solo se incluyen tras una decisión individual y consciente.",
            "La digitalización de una unidad no es motivo para eliminar el documento físico original."),
         h2("7. Método de eliminación propuesto"),
         p(pr.metodo or PEND.format("método: trituración, picado u otro, con certificación de destrucción técnica")),
         h2("8. Solicitud al Comité"),
         p("Se solicita al Comité aprobar la eliminación de las series y subseries relacionadas, para que el Servicio Geológico Colombiano continúe con la publicación del inventario por sesenta días hábiles, la atención de observaciones, la eliminación y la publicación del acta."),
         h2("9. Pasos siguientes (a cargo del Servicio Geológico Colombiano)"),
         li("Publicación del inventario en el sitio web institucional, en el enlace de transparencia y acceso a la información pública, por 60 días hábiles.",
            "Si hay observaciones ciudadanas, solicitud de concepto técnico al Archivo General de la Nación dentro de 30 días hábiles; el proceso se suspende hasta contar con la respuesta.",
            "Eliminación con registro fotográfico y certificación de destrucción técnica.",
            "Acta firmada por la presidencia y la secretaría técnica del Comité, conservada y publicada con los inventarios."),
         p("El alcance del contratista cierra con la entrega del FUID de eliminación, este informe, la presentación y la sustentación ante el Comité."),
         doc._firmas(pa)]
    return f"Informe de eliminación · {pr.nombre}", {"bloques": b, "meta": {"proceso": str(pr.id)}}


def presentacion_eliminacion(db: Session, pr) -> tuple[str, dict]:
    pa = ct.parametros(db)
    grupos, tot = agrupar(db, pr.id)
    por_periodo: dict[str, list] = defaultdict(lambda: [0, 0, 0.0])
    for g in grupos:
        a = por_periodo[g["periodo"] or "—"]
        a[0] += g["carpetas"]; a[1] += g["folios"]; a[2] += g["ml"]
    s = [slide("Propuesta de eliminación documental", [f"{pa['contratante']}", f"Contrato {pa['contrato_numero']} · {pa['contratista']}", f"Sesión del Comité Institucional de Gestión y Desempeño · {fecha_larga(date.today())}"]),
         slide("Qué se le pide al Comité", ["Aprobar la eliminación de las series y subseries que la TVD señala como eliminación, y de lo no elegido como muestra en las series de selección.",
                                          "El inventario completo se anexa en el FUID de eliminación."]),
         slide("Marco normativo", ["Ley 594 de 2000 y Decreto 1080 de 2015.", "Acuerdo 001 de 2024 del AGN, artículo 4.5.4.", "Procedimiento PR-GDM-001 versión 3 (PR-SAD-PED-001) del SGC."]),
         slide("Cómo se identificó lo que se propone", ["Cruce del inventario de origen con las subseries de eliminación y selección de cada periodo.", "Verificación de cada carpeta por una persona del equipo.", "Exclusión de lo que esté por definir y de lo que sugiera información de derechos humanos hasta decisión individual."]),
         slide("Resultados", [f"{tot['series']} series y subseries", f"{tot['carpetas']} carpetas · {tot['folios']} folios", f"{num(tot['ml'])} metros lineales estimados"],
               t={"cols": ["Periodo", "Carpetas", "Folios", "ML"], "rows": [[k, v[0], v[1], num(v[2])] for k, v in sorted(por_periodo.items())][:12]}),
         slide("Series y subseries propuestas", [], t={"cols": ["Periodo", "Serie", "Subserie", "Carpetas", "Fechas extremas"],
                                                       "rows": [[g["periodo"], g["serie"][:50], g["subserie"][:50], g["carpetas"], f"{g['ini']} a {g['fin']}"] for g in grupos][:12]}),
         slide("Salvaguardas", ["La digitalización no justifica eliminar el original físico.", "Nada se eliminó: la eliminación depende de la aprobación del Comité.", "La decisión final sobre suspensión corresponde al Archivo General de la Nación."]),
         slide("Ruta después de la aprobación", ["Publicación del inventario por 60 días hábiles.", "Concepto del AGN en 30 días hábiles si hay observaciones.", "Eliminación, acta firmada y publicación del acta."]),
         slide("Decisión del Comité", ["Aprobada / No aprobada / Aprobada con ajustes", "Acta de sesión n.º ______  Fecha ______"])]
    return f"Presentación al Comité · {pr.nombre}", {"bloques": s, "meta": {"proceso": str(pr.id)}}


def _fd(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def acta_eliminacion(db: Session, pr) -> tuple[str, dict]:
    """
    Acta de eliminación con la misma estructura del formato oficial F-GDM-004 versión 2: los
    campos del encabezado, la aprobación del Comité, los considerandos, el peso y el material,
    la nota y los firmantes. Lo que cambie la administradora en el visor es lo que sale en el
    formato oficial (`acta_a_xlsx_oficial`). Después del formato, y fuera de él, van el resumen
    por series y los datos de publicación, que sirven de apoyo al Comité.
    """
    pa = ct.parametros(db)
    grupos, tot = agrupar(db, pr.id)
    pl = plazos(pr)
    cajas = {i["caja"] for i in items_con_datos(db, pr.id, "confirmada") if i["caja"]}
    ml_caja = float(pa["ml_por_caja"])
    n_cajas = len(cajas)
    ml = n_cajas * ml_caja if n_cajas else tot["ml"]
    comite = "SI" if pr.fecha_aprobacion else PEND.format("SI o NO")
    campos = [["Acta de eliminación documental n.º", PEND.format("número")],
              ["Fecha", _fd(pr.fecha_eliminacion) or PEND.format("fecha de la eliminación")],
              ["Lugar", PEND.format("lugar")],
              ["Aprueba el Comité Institucional de Gestión y Desempeño (SI o NO)", comite],
              ["Fecha de aprobación", _fd(pr.fecha_aprobacion) or PEND.format("fecha")],
              ["Acta del Comité n.º", pr.acta_comite or PEND.format("número del acta del Comité")],
              ["Cajas referencia X-200", str(n_cajas) if n_cajas else PEND.format("número de cajas")],
              ["Metros lineales", num(ml)],
              ["Peso en kilos", PEND.format("peso certificado por la empresa de destrucción técnica")],
              ["Tipo de material eliminado", "PAPEL - CARTÓN - OTROS SOPORTES"]]
    considerando_1 = (
        "En cumplimiento de la solicitud de aprobación del lote de eliminación, presentado por el Grupo de Relacionamiento con la "
        "Ciudadanía – Gestión Documental y sometida a consideración del Comité Institucional de Gestión y Desempeño, como lo indica el Acta No. "
        f"{pr.acta_comite or '________'} con fecha del {_fd(pr.fecha_aprobacion) or '___________'}, se procede a efectuar la eliminación de cada "
        "una de las Series y Subseries Documentales descritas en el Formato Único de Inventario Documental (FUID) anexo.")
    considerando_2 = (
        f"Teniendo en cuenta que la documentación registrada en el FUID, está contenida en {n_cajas or '________'} Cajas referencia X-200, "
        f"correspondientes a {num(ml)} metros lineales, se procede a eliminar por medio de la empresa que certifique la destrucción técnica de los "
        "documentos de archivo el SGC.")
    nota = ("NOTA: Se entiende por Eliminación Documental, la destrucción de los documentos que han perdido sus valores primarios administrativos, "
            "legales, contables y fiscales que no tienen valor histórico, y carecen de relevancia para la ciencia y la tecnología, conforme lo "
            "determinan las TRD y/o TVD.")
    b = [h1("Acta de eliminación documental"),
         p("Estructura del formato oficial F-GDM-004 versión 2 del Servicio Geológico Colombiano. Todo lo que cambie aquí sale en el formato oficial. "
           "Lo que está entre corchetes es lo que la plataforma no puede saber."),
         tabla(["Campo", "Valor"], campos),
         h2("CONSIDERANDO"), p(considerando_1), p(considerando_2), p(nota),
         h2("Firmantes responsables"),
         tabla(["Rol", "Nombre", "Cargo", "Entidad"],
               [["Presidencia del Comité Institucional de Gestión y Desempeño", PEND.format("nombre"), PEND.format("cargo"), pa["contratante"]],
                ["Secretaría técnica del Comité", PEND.format("nombre"), PEND.format("cargo"), pa["contratante"]]]),
         p("Anexo: Inventario Documental / Registro fotográfico / Certificado de destrucción técnica de los documentos de archivo"),
         h2("Apoyo para el Comité (no hace parte del formato oficial)"),
         p("Fundamento: Acuerdo 001 de 2024 del Archivo General de la Nación, artículo 4.5.4, y procedimiento PR-GDM-001 versión 3. "
           "Tablas de Valoración Documental aprobadas, convalidadas e inscritas en el Registro Único de Series Documentales: "
           + PEND.format("acto de convalidación, fecha y número de inscripción")),
         _tabla_series(grupos) if grupos else p("Aún no hay carpetas confirmadas."),
         p(f"Totales: {tot['series']} series y subseries, {tot['carpetas']} carpetas, {tot['folios']} folios."),
         p(f"Método de eliminación: {pr.metodo or PEND.format('método aplicado')}."),
         tabla(["Concepto", "Dato"], [["Publicación del inventario desde", _fd(pr.publicacion_inicio) or PEND.format("fecha")],
                                      ["Publicación hasta", pl.get("publicacion_fin", PEND.format("fecha"))],
                                      ["Observaciones ciudadanas", {None: PEND.format("sí o no"), True: "Sí", False: "No"}[pr.hubo_observaciones]],
                                      ["Concepto técnico del Archivo General de la Nación", _fd(pr.concepto_recibido) or PEND.format("fecha o no aplica")]])]
    return f"Acta de eliminación · {pr.nombre}", {"bloques": b, "meta": {"proceso": str(pr.id)}}


_PENDIENTE = __import__("re").compile(r"\[Completar:[^\]]*\]")


def _limpio(t: str) -> str:
    return _PENDIENTE.sub("__________", str(t or "")).strip()


def acta_a_xlsx_oficial(contenido: dict, pr) -> bytes:
    """El acta (con las ediciones que se le hayan hecho) en la plantilla oficial F-GDM-004 versión 2."""
    from geology.dominio import formatos_sgc as fmt
    bl = contenido.get("bloques", [])
    tablas = [x for x in bl if x["t"] == "tabla"]
    if not tablas:
        raise ValueError("El acta no tiene la tabla de campos.")
    campos = {r[0]: r[1] for r in tablas[0]["rows"] if len(r) > 1}

    def v(prefijo: str) -> str:
        for k, val in campos.items():
            if k.lower().startswith(prefijo.lower()):
                return _limpio(val)
        return ""
    # Los considerandos son los párrafos entre el subtítulo «CONSIDERANDO» y la nota.
    idx = next((i for i, x in enumerate(bl) if x["t"] in ("h2", "h3") and x["x"].strip().upper().startswith("CONSIDERANDO")), None)
    parrafos, nota = [], ""
    if idx is not None:
        for x in bl[idx + 1:]:
            if x["t"] != "p":
                break
            if x["x"].strip().upper().startswith("NOTA"):
                nota = x["x"].strip()
                break
            parrafos.append(_limpio(x["x"]))
    comite = v("Aprueba").upper()
    si_no = "SI _X_   NO ______" if comite.startswith("SI") else ("SI ___   NO _X_" if comite.startswith("NO") else "SI___   NO ______")
    narrativa = (f"\nAPRUEBA:  \nCOMITÉ INSTITUCIONAL DE GESTIÓN Y DESEMPEÑO   {si_no}   \n"
                 f"FECHA DE APROBACIÓN {v('Fecha de aprobación') or '__________________'}  ACTA No. {v('Acta del Comité') or '____________'}\n\n\n"
                 "CONSIDERANDO:\n\n" + "\n\n".join(parrafos) + "\n\n"
                 f"Peso en kilos: {v('Peso en kilos')}\nTipo de material eliminado: {v('Tipo de material') or 'PAPEL - CARTON - OTROS SOPORTES'}\n\n\n"
                 + (_limpio(nota) if nota else "") + "\n")
    firmas = {}
    for x in tablas[1:]:
        if [c.lower() for c in x["cols"][:2]] == ["rol", "nombre"]:
            for i, r in enumerate(x["rows"][:2], start=1):
                firmas[f"firma{i}"] = {"nombre": _limpio(r[1]), "cargo": _limpio(r[2]) if len(r) > 2 else "", "entidad": _limpio(r[3]) if len(r) > 3 else ""}
            break
    return fmt.acta_eliminacion({"numero": v("Acta de eliminación"), "fecha": v("Fecha") if not v("Fecha").startswith("Fecha de") else "",
                                 "lugar": v("Lugar"), "narrativa": narrativa, **firmas})
