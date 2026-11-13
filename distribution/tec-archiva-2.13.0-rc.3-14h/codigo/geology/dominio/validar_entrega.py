"""
Validación cruzada de una unidad: hoja de control contra imágenes digitalizadas.

Cuando se cargan las hojas de control hechas y sus imágenes, nadie quiere enterarse en la
entrega final de que a una hoja le faltan tres folios o de que la parte 3 de un libro nunca se
subió. Esta validación corre al cargar y se puede volver a correr cuando se quiera. Devuelve
hallazgos con gravedad, número de trámite cuando aplica y qué hacer, sin modificar nada.

Gravedad
  error    hay que corregirlo antes de avanzar: la hoja o las imágenes no cuentan lo mismo.
  aviso    conviene mirarlo; no detiene el flujo.
  ok       comprobación pasada (se devuelve resumida para que se vea qué se miró).
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def _h(gravedad: str, codigo: str, mensaje: str, que_hacer: str = "", no_item: int | None = None,
       dondequiera: str = "") -> dict:
    return {"gravedad": gravedad, "codigo": codigo, "mensaje": mensaje, "que_hacer": que_hacer,
            "no_item": no_item, "donde": dondequiera}


def _hoja(exp, unidad, hallazgos: list, comprobadas: list) -> None:
    tramites = sorted(exp.tramites or [], key=lambda t: t.no_item)
    if not tramites:
        hallazgos.append(_h("error", "HOJA_VACIA", "La unidad no tiene hoja de control cargada.",
                            "Importe el Excel o levante la hoja con el lector.", dondequiera="hoja"))
        return
    comprobadas.append(f"Hoja de control con {len(tramites)} trámite(s).")

    # Continuidad de folios. En un libro por partes el primer folio puede no ser 1 (foliación
    # corrida), así que la referencia es el primer folio de la propia hoja.
    esperado = None
    for t in tramites:
        desde, hasta = t.folio_desde, t.folio_hasta
        if desde is None or hasta is None:
            hallazgos.append(_h("error", "FOLIO_ILEGIBLE", "Folios sin número legible.",
                                "Escriba el folio inicial y final.", t.no_item, "hoja"))
            continue
        if hasta < desde:
            hallazgos.append(_h("error", "FOLIO_INVERTIDO",
                                f"El folio final {hasta} es menor que el inicial {desde}.",
                                "Corrija el rango.", t.no_item, "hoja"))
        if esperado is not None and desde != esperado:
            tipo = "hay folios sin asignar" if desde > esperado else "hay folios repetidos"
            hallazgos.append(_h("error", "FOLIO_SALTO",
                                f"Debía empezar en el folio {esperado} y empieza en {desde} ({tipo}).",
                                "Revise la foliación contra la imagen.", t.no_item, "hoja"))
        esperado = (hasta or 0) + 1
        if not (t.tipo_documental or "").strip():
            hallazgos.append(_h("error", "TIPO_VACIO", "El tipo documental está vacío.",
                                "Escríbalo leyendo el documento.", t.no_item, "hoja"))
        if t.fecha is None and not (t.fecha_texto or "").strip():
            hallazgos.append(_h("aviso", "FECHA_VACIA", "El trámite no tiene fecha.",
                                "Escriba la fecha o «SF» si el documento no la trae.", t.no_item, "hoja"))
    comprobadas.append("Continuidad de folios entre trámites.")

    if exp.diferencia_folios:
        hallazgos.append(_h("aviso", "DIF_INVENTARIO", exp.diferencia_folios,
                            "Verifique el conteo físico frente al inventario de origen.", None, "hoja"))
    elif unidad is not None and unidad.folios and exp.volumen_folios:
        comprobadas.append("Folios de la hoja frente al inventario de origen.")

    if exp.periodo_id is None:
        hallazgos.append(_h("aviso", "SIN_PERIODO", "La unidad no tiene periodo asignado.",
                            "Asígnelo desde la hoja de control.", None, "hoja"))
    if exp.subserie_id is None:
        hallazgos.append(_h("aviso", "SIN_SUBSERIE", "La unidad no tiene subserie de la TVD.",
                            "Escójala en la hoja de control.", None, "hoja"))


def _imagenes(db, exp, hallazgos: list, comprobadas: list, verificar_huella: bool) -> None:
    from geology.modelos import Archivo
    from geology.dominio import division
    from geology.dominio.recepcion_tecnica import UMBRAL_DPI

    archivos = (db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta)
                  .order_by(Archivo.fragmento).all())
    if not archivos:
        hallazgos.append(_h("error", "SIN_IMAGEN", "No hay imágenes digitalizadas cargadas.",
                            "Suba el PDF en la pestaña Cargue (AC-CP-#####.pdf).", None, "imagen"))
        return

    # Archivos registrados pero ausentes del almacén
    ausentes = [a for a in archivos if not Path(a.ruta).exists()]
    for a in ausentes:
        hallazgos.append(_h("error", "IMAGEN_AUSENTE",
                            f"El archivo «{a.nombre_original}» figura cargado pero no está en el "
                            "almacén del servidor.", "Vuelva a subirlo: el registro se reemplaza.",
                            None, "imagen"))
    if not ausentes:
        comprobadas.append(f"{len(archivos)} archivo(s) de imagen presentes en el almacén.")

    # Secuencia de partes
    faltan = division.faltantes([a.fragmento for a in archivos])
    if faltan:
        hallazgos.append(_h("error", "PARTE_FALTANTE",
                            f"Faltan las partes {', '.join(map(str, faltan))} del expediente.",
                            "Suba las partes que faltan con su número (AC-CP-#####-2.pdf).",
                            None, "imagen"))
    elif any(a.fragmento > 0 for a in archivos):
        comprobadas.append("Secuencia de partes completa.")

    # Páginas frente a folios
    paginas = [a.paginas for a in archivos]
    if all(p for p in paginas):
        total = sum(paginas)
        exp_folios = exp.volumen_folios or 0
        if exp.tramites:
            try:
                exp_folios = max(exp_folios, max((t.folio_hasta or 0) for t in exp.tramites))
            except Exception:
                pass
        if exp_folios:
            if total < exp_folios:
                hallazgos.append(_h(
                    "error", "PAGINAS_MENOS",
                    f"La imagen tiene {total} página(s) y la hoja de control declara {exp_folios} "
                    f"folio(s): faltan {exp_folios - total}.",
                    "Revise si faltan imágenes por digitalizar o si la foliación de la hoja es "
                    "mayor a la real.", None, "imagen"))
            elif total > exp_folios:
                hallazgos.append(_h(
                    "aviso", "PAGINAS_MAS",
                    f"La imagen tiene {total} página(s) y la hoja declara {exp_folios} folio(s): "
                    f"sobran {total - exp_folios}.",
                    "Puede ser carátula, páginas en blanco o reversos sin foliar; confirme que "
                    "no hay folios sin describir.", None, "imagen"))
            else:
                comprobadas.append(f"Páginas de la imagen ({total}) iguales a los folios de la hoja.")
    else:
        hallazgos.append(_h("aviso", "PAGINAS_SIN_CONTAR",
                            "No se pudieron contar las páginas de alguna imagen.",
                            "Abra el PDF para comprobar que no esté dañado.", None, "imagen"))

    # Calidad técnica
    for a in archivos:
        if a.error_proceso:
            hallazgos.append(_h("aviso", "PROCESO_FALLIDO",
                                f"La preparación de «{a.nombre_original}» falló: {a.error_proceso[:160]}",
                                "Vuelva a procesar o a subir el archivo.", None, "imagen"))
        if a.avisos_tecnicos:
            hallazgos.append(_h("aviso", "AVISO_TECNICO",
                                f"«{a.nombre_original}»: {a.avisos_tecnicos[:200]}", "", None, "imagen"))
        if UMBRAL_DPI > 0 and a.dpi_minimo and a.dpi_minimo < UMBRAL_DPI:
            hallazgos.append(_h("error", "DPI_BAJO",
                                f"«{a.nombre_original}» tiene {a.dpi_minimo} ppp y el mínimo es {UMBRAL_DPI}.",
                                "Hay que volver a escanear.", None, "imagen"))

    # Huella de no alteración (opcional, porque lee el archivo entero)
    if verificar_huella:
        for a in archivos:
            r = Path(a.ruta)
            if not r.exists():
                continue
            h = hashlib.sha256()
            with r.open("rb") as f:
                for trozo in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(trozo)
            if h.hexdigest() != a.sha256:
                hallazgos.append(_h("error", "HUELLA_DISTINTA",
                                    f"«{a.nombre_original}» cambió desde que se cargó: su huella "
                                    "ya no coincide.", "Restaure el original o vuelva a cargarlo.",
                                    None, "imagen"))
        comprobadas.append("Huella de no alteración de los archivos.")


def validar_unidad(db, exp, verificar_huella: bool = False) -> dict:
    """Devuelve el informe de una unidad. No escribe nada."""
    from geology.modelos import UnidadInventario
    unidad = (db.query(UnidadInventario)
                .filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first())
    hallazgos: list[dict] = []
    comprobadas: list[str] = []
    _hoja(exp, unidad, hallazgos, comprobadas)
    _imagenes(db, exp, hallazgos, comprobadas, verificar_huella)

    errores = [h for h in hallazgos if h["gravedad"] == "error"]
    avisos = [h for h in hallazgos if h["gravedad"] == "aviso"]
    return {
        "carpeta": exp.codigo_carpeta,
        "estado": exp.estado,
        "conforme": not errores,
        "errores": len(errores),
        "avisos": len(avisos),
        "hallazgos": hallazgos,
        "comprobado": comprobadas,
        "resumen": ("Hoja e imágenes coinciden." if not hallazgos else
                    f"{len(errores)} error(es) y {len(avisos)} aviso(s) por revisar."),
    }
