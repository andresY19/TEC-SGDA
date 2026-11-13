"""
Paquete de entrega de la digitalización.

Reúne lo que el Archivo General de la Nación pide para una entrega formal:

  1. Copia de CONSULTA en PDF (PDF/A cuando las partes de origen lo declaran) con texto
     buscable, un solo archivo por libro o tomo.
  2. Copia MAESTRA de preservación, sin compresión o con compresión sin pérdida (TIFF). Si la
     imagen de origen es un JPEG, que ya perdió información al capturarse, NO se puede
     convertir en maestra: se entrega tal cual, marcada como no conforme. Convertir un JPEG a
     TIFF solo agranda el archivo y falsea la calidad; la maestra se captura así en el escáner.
  3. Estructura de carpetas que refleja la del archivo: fondo, periodo, dependencia, serie,
     subserie y expediente. Nombres sin espacios, tildes ni caracteres especiales.
  4. Índice electrónico en CSV y XML: identificador único, nombre, formato, tamaño, huella
     SHA-256, fecha de creación, creador y orden. Más el índice de documentos de cada
     expediente en su orden.
  5. Informe de control de calidad por expediente.
  6. Acta de cierre de digitalización en Word, lista para firma, con folios físicos frente a
     imágenes entregadas, resultado del control de calidad y estado de conservación.

El acta NO certifica por la persona: lo que mide el sistema lo dice como medición automática, y
lo que solo puede afirmar quien revisó el papel queda como casilla para marcar y firmar.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")


def limpio(texto, tope: int = 60) -> str:
    """Nombre seguro: mayúsculas sin tildes, solo letras, números, guion y guion bajo."""
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_").upper()
    return (t[:tope].strip("_")) or "SIN_DATO"


def fecha_en_letras(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def huella_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def ruta_en_arbol(exp, ctx: dict) -> str:
    """Fondo / periodo / sección / subsección / serie / subserie / expediente.

    En las tablas de valoración la unidad administrativa es la sección y la oficina productora
    es la subsección."""
    periodo, serie, sub, sec = ctx.get("periodo"), ctx.get("serie"), ctx.get("sub"), ctx.get("seccion")
    partes = [
        "SGC",
        f"PERIODO_{limpio(periodo.numero_romano)}" if periodo else "PERIODO_SIN_ASIGNAR",
        limpio(f"{getattr(sec, 'codigo_dependencia', '') or 'SD'}_{getattr(sec, 'unidad_administrativa', '')}", 80),
        limpio(getattr(sec, "oficina_productora", "") or "SIN_SUBSECCION", 80),
        limpio(f"{serie.codigo}_{serie.nombre}") if serie else "SERIE_SIN_ASIGNAR",
        limpio(f"{sub.codigo}_{sub.nombre}") if sub else "SUBSERIE_SIN_ASIGNAR",
        limpio(exp.codigo_carpeta),
    ]
    return "/".join(partes)


def nombre_base(exp, ctx: dict) -> str:
    """CódigoDependencia_CódigoSerie_Año_Expediente, como propone la guía."""
    sec, serie = ctx.get("seccion"), ctx.get("serie")
    anio = (exp.fecha_final or exp.fecha_inicial)
    return "_".join([
        limpio(getattr(sec, "codigo_dependencia", "") or "SD"),
        limpio(getattr(serie, "codigo", "") or "SS"),
        str(anio.year) if anio else "SF",
        limpio(exp.codigo_carpeta)])


def paginas_maestras(ruta: Path):
    """
    Genera (n.º de página, bytes, extensión, formato, conforme, ppp) de cada imagen de un PDF.
    Las imágenes sin pérdida salen como TIFF con compresión sin pérdida; el JPEG sale tal cual
    y queda marcado como no conforme con la copia maestra.
    """
    import pikepdf
    from PIL import Image
    from geology.dominio.calidad_imagen import _imagen_de
    with pikepdf.open(str(ruta)) as pdf:
        for n, pag in enumerate(pdf.pages, start=1):
            obj = _imagen_de(pag)
            if obj is None:
                continue
            caja = pag.get("/MediaBox") or [0, 0, 612, 792]
            ancho_in = abs(float(caja[2]) - float(caja[0])) / 72.0
            ppp = round(int(obj.get("/Width", 0)) / ancho_in) if ancho_in else None
            filtro = str(obj.get("/Filter", ""))
            if filtro == "/DCTDecode":
                yield n, bytes(obj.read_raw_bytes()), "jpg", "JPEG con pérdida", False, ppp
            elif filtro == "/JPXDecode":
                yield n, bytes(obj.read_raw_bytes()), "jp2", "JPEG 2000", True, ppp
            else:
                im = pikepdf.PdfImage(obj).as_pil_image()
                if im.mode not in ("1", "L", "RGB", "RGBA", "CMYK", "P"):
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "TIFF", compression="tiff_adobe_deflate",
                        dpi=(ppp or 300, ppp or 300))
                yield n, buf.getvalue(), "tif", "TIFF sin pérdida", True, ppp


def _csv(filas: list[dict], columnas: list[str]) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columnas, delimiter=";", extrasaction="ignore")
    w.writeheader()
    w.writerows(filas)
    return ("﻿" + out.getvalue()).encode("utf-8")


def _xml(filas: list[dict], columnas: list[str], raiz: str, elemento: str) -> bytes:
    partes = ['<?xml version="1.0" encoding="UTF-8"?>', f"<{raiz}>"]
    for f in filas:
        partes.append(f"  <{elemento}>")
        for c in columnas:
            partes.append(f"    <{c}>{escape(str(f.get(c, '') if f.get(c) is not None else ''))}</{c}>")
        partes.append(f"  </{elemento}>")
    partes.append(f"</{raiz}>")
    return "\n".join(partes).encode("utf-8")


COLUMNAS_INDICE = [
    "identificador_unico", "codigo_carpeta", "tipo_copia", "nombre_archivo", "ruta_relativa",
    "formato", "conforme_con_norma", "tamano_bytes", "sha256", "fecha_creacion", "creador",
    "orden", "pagina", "paginas_del_archivo", "resolucion_ppp", "periodo", "dependencia",
    "serie", "subserie", "fecha_inicial", "fecha_final"]

COLUMNAS_DOCUMENTOS = [
    "codigo_carpeta", "orden", "fecha", "tipo_documental", "folio_desde", "folio_hasta",
    "no_radicado", "observaciones"]


def construir(db, expedientes: list, quien_nombre: str, destino: Path,
              incluir_maestra: bool = True, contrato: str = "") -> dict:
    """
    Escribe el paquete en `destino` (un .zip) y devuelve el resumen. `expedientes` ya viene
    filtrado: publicables, con imágenes, con la secuencia de partes completa.
    """
    from geology.dominio import calidad_imagen, validador_pdfa
    from geology.modelos import Archivo
    from geology.rutas import consulta, instrumentos

    hoy = date.today()
    raiz = f"ENTREGA_{hoy.isoformat()}"
    indice: list[dict] = []
    documentos: list[dict] = []
    resumen_carpetas: list[dict] = []
    hashes: list[str] = []
    estados_pdfa: list[tuple] = []
    destino.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for exp in expedientes:
            ctx = instrumentos._contexto(db, exp)
            arbol = ruta_en_arbol(exp, ctx)
            base = nombre_base(exp, ctx)
            registros = (db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta)
                           .order_by(Archivo.fragmento).all())
            origenes = [Path(r.ruta) for r in registros if r.ruta and Path(r.ruta).exists()]
            comunes = {
                "codigo_carpeta": exp.codigo_carpeta,
                "creador": next((r.subido_por for r in registros if r.subido_por), ""),
                "periodo": ctx["periodo"].numero_romano if ctx.get("periodo") else "",
                "dependencia": getattr(ctx.get("seccion"), "codigo_dependencia", "") or "",
                "serie": ctx["serie"].nombre if ctx.get("serie") else "",
                "subserie": ctx["sub"].nombre if ctx.get("sub") else "",
                "fecha_inicial": exp.fecha_inicial.isoformat() if exp.fecha_inicial else "",
                "fecha_final": exp.fecha_final.isoformat() if exp.fecha_final else "",
            }
            creado = max((r.subido_en for r in registros if r.subido_en), default=datetime.now())

            # 1. Copia de consulta: el tomo completo en un solo PDF.
            tmp, _ = consulta.preparar_pdf_consulta(db, exp, exp.codigo_carpeta, 0, False)
            try:
                nombre_pdf = f"{base}.pdf"
                rel = f"{raiz}/CONSULTA/{arbol}/{nombre_pdf}"
                # PDF/A comprobado con veraPDF; si no cumple se convierte, y si aun así no
                # cumple se dice sin esconderlo y se le quita la declaración falsa.
                estado_pdfa = validador_pdfa.asegurar_pdfa(tmp)
                estados_pdfa.append((exp.codigo_carpeta, estado_pdfa))
                sha = huella_de(Path(tmp))
                zf.write(tmp, rel)
                paginas_pdf = 0
                try:
                    import pikepdf
                    with pikepdf.open(tmp) as pdf:
                        paginas_pdf = len(pdf.pages)
                except Exception:
                    pass
                from geology.dominio.neutralidad import declaracion_pdfa
                pdfa = declaracion_pdfa(tmp)
                if estado_pdfa["estado"] in ("CONFORME", "CONFORME_TRAS_CONVERSION"):
                    formato = f"{estado_pdfa['perfil']} verificado con {estado_pdfa['motor']}"
                    conforme = "SI"
                elif estado_pdfa["estado"] == "NO_CONFORME":
                    formato = "PDF (no cumple PDF/A)"
                    conforme = f"NO, {estado_pdfa['reglas_falladas']} regla(s) PDF/A incumplida(s)"
                else:
                    formato = f"PDF/A-{pdfa[0]}{pdfa[1].lower()} declarado, sin verificar" if pdfa else "PDF"
                    conforme = "NO VERIFICADO, falta el validador veraPDF"
                indice.append({**comunes, "identificador_unico": str(uuid.uuid5(uuid.NAMESPACE_URL, sha)),
                               "tipo_copia": "CONSULTA", "nombre_archivo": nombre_pdf,
                               "ruta_relativa": rel.split("/", 1)[1],
                               "formato": formato, "conforme_con_norma": conforme,
                               "tamano_bytes": Path(tmp).stat().st_size, "sha256": sha,
                               "fecha_creacion": creado.isoformat(timespec="seconds"),
                               "orden": 1, "pagina": "", "paginas_del_archivo": paginas_pdf,
                               "resolucion_ppp": ""})
                hashes.append(f"{sha}  {rel.split('/', 1)[1]}")
            finally:
                Path(tmp).unlink(missing_ok=True)

            # 2. Copia maestra: una imagen por página, en orden.
            maestras_conformes, maestras_total = 0, 0
            if incluir_maestra:
                n_global = 0
                for origen in origenes:
                    for pag, datos, ext, formato, conforme, ppp in paginas_maestras(origen):
                        n_global += 1
                        maestras_total += 1
                        maestras_conformes += 1 if conforme else 0
                        nom = f"{base}_{n_global:04d}.{ext}"
                        rel = f"{raiz}/MAESTRA/{arbol}/{nom}"
                        zf.writestr(rel, datos)
                        sha = hashlib.sha256(datos).hexdigest()
                        indice.append({**comunes, "identificador_unico": str(uuid.uuid5(uuid.NAMESPACE_URL, sha)),
                                       "tipo_copia": "MAESTRA", "nombre_archivo": nom,
                                       "ruta_relativa": rel.split("/", 1)[1], "formato": formato,
                                       "conforme_con_norma": "SI" if conforme else "NO, JPEG con pérdida",
                                       "tamano_bytes": len(datos), "sha256": sha,
                                       "fecha_creacion": creado.isoformat(timespec="seconds"),
                                       "orden": n_global + 1, "pagina": n_global,
                                       "paginas_del_archivo": "", "resolucion_ppp": ppp or ""})
                        hashes.append(f"{sha}  {rel.split('/', 1)[1]}")

            # 3. Índice de documentos del expediente, en orden.
            for t in sorted(exp.tramites, key=lambda x: x.no_item or 0):
                documentos.append({
                    "codigo_carpeta": exp.codigo_carpeta, "orden": t.no_item,
                    "fecha": t.fecha.isoformat() if t.fecha else (t.fecha_texto or "SF"),
                    "tipo_documental": t.tipo_documental, "folio_desde": t.folio_desde,
                    "folio_hasta": t.folio_hasta, "no_radicado": t.no_radicado,
                    "observaciones": t.observaciones or ""})

            # 4. Control de calidad por expediente.
            inf = calidad_imagen.informe_en_cache(exp.codigo_carpeta, origenes, exp.volumen_folios) \
                if origenes else None
            if inf:
                zf.writestr(f"{raiz}/CONTROL_CALIDAD/Calidad_{limpio(exp.codigo_carpeta)}.xlsx",
                            calidad_imagen.informe_en_excel(exp.codigo_carpeta, inf))
            resumen_carpetas.append({
                "codigo": exp.codigo_carpeta, "partes": len(registros),
                "folios_fisicos": exp.volumen_folios or 0,
                "imagenes": inf["paginas"] if inf else 0,
                "sospechosas": len(inf["sospechosas"]) if inf else 0,
                "cumple": bool(inf and inf["cumple"]),
                "dpi_minimo": inf["dpi_minimo"] if inf else None,
                "maestra_total": maestras_total, "maestra_conforme": maestras_conformes,
                "conservacion": (exp.caracteristicas_fisicas or "").strip(),
                "diferencia_folios": exp.diferencia_folios or "",
                "pdfa": next((e["estado"] for c, e in estados_pdfa if c == exp.codigo_carpeta), "NO_VALIDADO")})

        # 5. Índices, huellas, acta y leeme.
        zf.writestr(f"{raiz}/INDICE_ELECTRONICO.csv", _csv(indice, COLUMNAS_INDICE))
        zf.writestr(f"{raiz}/INDICE_ELECTRONICO.xml",
                    _xml(indice, COLUMNAS_INDICE, "indice_electronico", "archivo"))
        zf.writestr(f"{raiz}/INDICE_DOCUMENTOS_POR_EXPEDIENTE.csv",
                    _csv(documentos, COLUMNAS_DOCUMENTOS))
        zf.writestr(f"{raiz}/HASHES_SHA256.txt", "\n".join(hashes) + "\n")
        zf.writestr(f"{raiz}/ACTA_CIERRE_DIGITALIZACION.docx",
                    acta_docx(resumen_carpetas, quien_nombre, contrato, hoy))
        zf.writestr(f"{raiz}/LEEME.txt", leeme(resumen_carpetas, hoy, incluir_maestra))

    return {"archivo": str(destino), "carpetas": resumen_carpetas, "archivos_indexados": len(indice),
            "maestra_no_conforme": sum(c["maestra_total"] - c["maestra_conforme"] for c in resumen_carpetas)}


def leeme(carpetas: list[dict], hoy: date, maestra: bool) -> str:
    return (
        f"PAQUETE DE ENTREGA DE LA DIGITALIZACIÓN · {fecha_en_letras(hoy)}\n\n"
        "CONSULTA/   Copia de uso: un PDF por libro o tomo, con texto buscable.\n"
        + ("MAESTRA/    Copia de preservación: una imagen por página, sin pérdida cuando la captura lo permitió.\n"
           if maestra else "")
        + "CONTROL_CALIDAD/   Informe de calidad por expediente (resolución, color, exposición, foco, alineación).\n"
        "INDICE_ELECTRONICO.csv / .xml   Un registro por archivo: identificador, formato, tamaño, huella SHA-256, fecha, creador y orden.\n"
        "INDICE_DOCUMENTOS_POR_EXPEDIENTE.csv   Los documentos de cada expediente en su orden y con sus folios.\n"
        "HASHES_SHA256.txt   Huella de cada archivo; compárela tras copiar el paquete para comprobar que nada cambió.\n"
        "ACTA_CIERRE_DIGITALIZACION.docx   Acta para revisar, completar y firmar.\n\n"
        f"Expedientes incluidos: {len(carpetas)}.\n")


def acta_docx(carpetas: list[dict], quien: str, contrato: str, hoy: date) -> bytes:
    from docx import Document
    from docx.shared import Pt
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    d.add_heading("ACTA DE CIERRE DE DIGITALIZACIÓN", level=1)
    d.add_paragraph(f"{contrato or 'Contrato 733 de 2026'} · Servicio Geológico Colombiano")
    d.add_paragraph(f"Fecha: {fecha_en_letras(hoy)}. Ciudad: Bogotá, D. C.")
    d.add_paragraph(f"Documento generado por la plataforma a nombre de {quien}. Las mediciones "
                    "automáticas se declaran como tales; lo que solo puede afirmar quien revisó el "
                    "papel queda para marcar y firmar.")

    total_fis = sum(c["folios_fisicos"] for c in carpetas)
    total_img = sum(c["imagenes"] for c in carpetas)
    d.add_heading("1. Folios físicos frente a imágenes entregadas", level=2)
    d.add_paragraph(f"Folios físicos digitalizados según las hojas de control: {total_fis}. "
                    f"Imágenes electrónicas entregadas: {total_img}. "
                    + ("Coinciden." if total_fis == total_img else
                       f"Diferencia de {abs(total_fis - total_img)}; se explica expediente por expediente "
                       "en la tabla siguiente (un folio puede tener anverso y reverso, y las hojas en "
                       "blanco de conservación se digitalizan)."))
    t = d.add_table(rows=1, cols=7)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(("Expediente", "Partes", "Folios físicos", "Imágenes", "Diferencia",
                           "Páginas por revisar", "Calidad automática")):
        t.rows[0].cells[i].text = h
    for c in carpetas:
        f = t.add_row().cells
        f[0].text = c["codigo"]
        f[1].text = str(c["partes"])
        f[2].text = str(c["folios_fisicos"])
        f[3].text = str(c["imagenes"])
        f[4].text = str(c["imagenes"] - c["folios_fisicos"])
        f[5].text = str(c["sospechosas"])
        f[6].text = "cumple" if c["cumple"] else "con observaciones"

    d.add_heading("2. Control de calidad al 100 % de las imágenes", level=2)
    d.add_paragraph(
        f"La plataforma aplicó una prueba automática sobre las {total_img} imágenes: resolución mínima, "
        "profundidad de color, exposición, foco, alineación y páginas en blanco. Detalle por página en "
        "la carpeta CONTROL_CALIDAD. Esta prueba señala páginas sospechosas; no sustituye la revisión "
        "visual frente al original.")
    sospechosas = sum(c["sospechosas"] for c in carpetas)
    d.add_paragraph(f"Páginas sospechosas en total: {sospechosas}. Las páginas de baja calidad se "
                    "documentan con su número y motivo para volver a capturarlas.")
    d.add_paragraph("Verificación del responsable (marque lo que comprobó frente al papel):")
    for linea in ("☐ Legibilidad de las imágenes revisada al 100 %.",
                  "☐ Orientación correcta de todas las imágenes.",
                  "☐ No faltan páginas respecto de los folios del expediente.",
                  "☐ Las páginas sospechosas del informe fueron revisadas y, cuando correspondía, recapturadas."):
        d.add_paragraph(linea)

    d.add_heading("3. Copia maestra y formatos", level=2)
    mt = sum(c["maestra_total"] for c in carpetas)
    mc = sum(c["maestra_conforme"] for c in carpetas)
    if mt:
        d.add_paragraph(f"Imágenes de la copia maestra entregadas: {mt}. En formato sin pérdida (TIFF o "
                        f"JPEG 2000): {mc}. En formato con pérdida (JPEG), no conformes con la norma de "
                        f"copia maestra: {mt - mc}."
                        + (" Esas imágenes deben recapturarse en TIFF para cerrar la copia maestra."
                           if mt - mc else ""))
    else:
        d.add_paragraph("Esta entrega no incluye copia maestra.")

    estados = [c["pdfa"] for c in carpetas]
    ok = sum(1 for e in estados if e in ("CONFORME", "CONFORME_TRAS_CONVERSION"))
    conv = sum(1 for e in estados if e == "CONFORME_TRAS_CONVERSION")
    no = sum(1 for e in estados if e == "NO_CONFORME")
    nv = sum(1 for e in estados if e == "NO_VALIDADO")
    d.add_paragraph(f"Copias de consulta en PDF/A comprobadas con el validador veraPDF: {ok} de {len(estados)}"
                    + (f" ({conv} requirieron conversión a PDF/A sin alterar las imágenes)." if conv else ".")
                    + (f" No conformes: {no}." if no else "")
                    + (f" Sin validar (validador no disponible): {nv}." if nv else ""))

    d.add_heading("4. Estado de conservación de los originales tras el escaneo", level=2)
    d.add_paragraph("Descripción registrada por expediente (elemento 3.4.4 de la descripción). "
                    "Quien firma confirma o completa tras revisar los originales.")
    t2 = d.add_table(rows=1, cols=2)
    t2.style = "Light Grid Accent 1"
    t2.rows[0].cells[0].text = "Expediente"
    t2.rows[0].cells[1].text = "Estado de conservación registrado"
    for c in carpetas:
        f = t2.add_row().cells
        f[0].text = c["codigo"]
        f[1].text = c["conservacion"] or "Sin registro; completar tras la revisión de los originales."
    d.add_paragraph("☐ No se evidenció daño adicional en los originales por causa del escaneo.")
    d.add_paragraph("Novedades: ______________________________________________________________")

    d.add_heading("5. Contenido de la entrega", level=2)
    for linea in ("CONSULTA: un PDF por libro o tomo, con texto buscable.",
                  "MAESTRA: una imagen por página.",
                  "INDICE_ELECTRONICO (CSV y XML) con identificador, formato, tamaño, huella SHA-256, fecha, "
                  "creador y orden.",
                  "HASHES_SHA256.txt para comprobar la integridad tras copiar."):
        d.add_paragraph(linea, style="List Bullet")

    d.add_paragraph("\n")
    d.add_paragraph("Responsable del proceso: ________________________   Firma: ______________")
    d.add_paragraph("Supervisor del contrato: _________________________   Firma: ______________")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()
