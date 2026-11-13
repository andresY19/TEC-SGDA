"""
Neutralidad de lo que recibe la entidad contratante.

Regla de la dirección del proyecto: quien consulta no debe enterarse de que en la elaboración
se usó inteligencia artificial. Eso es cosa del proceso interno y vive solo allí (bitácora,
marcas de propuesta, motor que redactó). Hay dos capas:

  1. Bloqueo humano. Si algún texto de la ficha o de la hoja de control menciona la IA, un
     modelo o un proveedor, la unidad no se puede validar ni enviar a consulta hasta que la
     persona lo reescriba. No se borra nada automáticamente porque quitar palabras de una
     frase la deja rota; lo decide quien describe.
  2. Red de seguridad al entregar. Todo Excel que sale hacia la entidad se limpia: sin marcas
     de propuesta, sin hojas internas de revisión previa y sin propiedades del archivo que
     delaten herramientas. Los PDF se sirven sin metadatos de procesamiento.
"""
from __future__ import annotations

import io
import re
import zipfile

MARCA = re.compile(r"\[\s*PROPUESTA DEL MODELO[^\]]*\]\s*", re.IGNORECASE)

# Menciones que no deben aparecer en ningún texto que llegue a la entidad.
_RASTROS = re.compile(
    r"(\bIA\b|\bI\.A\.|inteligencia artificial|modelo de lenguaje|\bLLM\b|\bGemini\b|\bClaude\b|"
    r"\bOpenAI\b|\bChatGPT\b|\bGPT-?\d|\bOllama\b|\bAnthropic\b|propuesta del modelo|"
    r"generad[oa] (autom[aá]ticamente|por (el )?(modelo|sistema))|redactad[oa] por (el )?modelo|"
    r"seg[uú]n el modelo|lector autom[aá]tico|reconocimiento (autom[aá]tico|[oó]ptico) de)",
    re.IGNORECASE)

HOJAS_INTERNAS = ("Revisión previa", "Revision previa", "Control de calidad", "Bitácora")
NEUTRO = "Archivo Central"


def quitar_marca(texto):
    return MARCA.sub("", str(texto)).strip() if texto is not None else texto


_HOJA = re.compile(r"(hoja\s+de\s+control|F-GDM-007)", re.IGNORECASE)


def menciona_hoja(texto) -> bool:
    """La ficha ISAD(G) no debe referirse a la hoja de control: son instrumentos distintos."""
    return bool(texto) and bool(_HOJA.search(str(texto)))


def rastros(texto) -> list[str]:
    """Las menciones a IA que trae un texto, para avisarle a quien describe."""
    if not texto:
        return []
    vistos = []
    for m in _RASTROS.finditer(str(texto)):
        t = m.group(0).strip()
        if t.lower() not in [v.lower() for v in vistos]:
            vistos.append(t)
    return vistos


def limpiar_libro(contenido: bytes) -> bytes:
    """Devuelve el Excel sin marcas, sin hojas internas y con propiedades neutras."""
    import openpyxl
    libro = openpyxl.load_workbook(io.BytesIO(contenido))
    for nombre in list(libro.sheetnames):
        if nombre in HOJAS_INTERNAS and len(libro.sheetnames) > 1:
            del libro[nombre]
    for ws in libro.worksheets:
        for fila in ws.iter_rows():
            for c in fila:
                if isinstance(c.value, str) and MARCA.search(c.value):
                    c.value = quitar_marca(c.value)
                if c.comment is not None:          # comentarios de celda pueden traer notas internas
                    c.comment = None
    p = libro.properties
    p.creator = p.lastModifiedBy = NEUTRO
    p.title = p.subject = p.description = p.keywords = p.category = None
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def limpiar_paquete_zip(contenido: bytes) -> bytes:
    entrada = zipfile.ZipFile(io.BytesIO(contenido))
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename.lower().endswith((".xlsx", ".xlsm")):
                datos = limpiar_libro(datos)
            z.writestr(info.filename, datos)
    return salida.getvalue()


def limpiar_respuesta(respuesta):
    """Aplica la limpieza a una Response de Excel o zip de Excel; deja pasar lo demás."""
    from fastapi.responses import Response
    tipo = (getattr(respuesta, "media_type", "") or "")
    cuerpo = getattr(respuesta, "body", None)
    if cuerpo is None:
        return respuesta
    try:
        if "spreadsheetml" in tipo:
            nuevo = limpiar_libro(cuerpo)
        elif tipo == "application/zip":
            nuevo = limpiar_paquete_zip(cuerpo)
        else:
            return respuesta
    except Exception:
        # Si no se puede limpiar, no se entrega: es preferible un error a filtrar un rastro.
        from fastapi import HTTPException
        raise HTTPException(503, "No se pudo preparar el archivo para consulta. Intente de nuevo.")
    return Response(nuevo, media_type=tipo,
                    headers={k: v for k, v in respuesta.headers.items()
                             if k.lower() == "content-disposition"})


def _jpeg_sin_metadatos(datos: bytes) -> bytes:
    """Quita de un JPEG los segmentos con datos personales o del equipo (Exif/XMP, IPTC,
    comentarios) sin recomprimir: los píxeles quedan idénticos."""
    if datos[:2] != b"\xff\xd8":
        return datos
    salida = bytearray(b"\xff\xd8")
    i = 2
    while i + 4 <= len(datos):
        if datos[i] != 0xFF:
            break
        marca = datos[i + 1]
        if marca == 0xDA:                      # inicio del barrido: el resto es imagen
            break
        if marca == 0xFF:                      # relleno
            i += 1
            continue
        largo = int.from_bytes(datos[i + 2:i + 4], "big")
        segmento = datos[i:i + 2 + largo]
        if marca in (0xE1, 0xED, 0xFE):        # APP1 (Exif, XMP), APP13 (IPTC), COM
            pass
        else:
            salida += segmento
        i += 2 + largo
    salida += datos[i:]
    return bytes(salida)


def pdf_sin_metadatos(ruta):
    """
    Copia temporal del PDF sin metadatos de procesamiento: información del documento, XMP,
    datos privados de programas, miniaturas y los Exif/XMP de las imágenes incrustadas.
    Devuelve la ruta de la copia, o None si no se pudo (quien llama NO debe entregar el
    original en ese caso). El archivo original no se toca.
    """
    import os
    import tempfile
    try:
        import pikepdf
        with pikepdf.open(ruta) as pdf:
            for k in list(pdf.docinfo.keys()):
                del pdf.docinfo[k]
            for k in ("/Metadata", "/PieceInfo", "/Info"):
                if k in pdf.Root:
                    del pdf.Root[k]
            for obj in pdf.objects:
                if not isinstance(obj, pikepdf.Dictionary | pikepdf.Stream):
                    continue
                for k in ("/Metadata", "/PieceInfo", "/Thumb"):
                    if k in obj and obj.get("/Type") != "/Catalog":
                        del obj[k]
                if (isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == "/Image"
                        and obj.get("/Filter") == "/DCTDecode"):
                    crudo = obj.read_raw_bytes()
                    limpio = _jpeg_sin_metadatos(crudo)
                    if limpio != crudo:
                        obj.write(limpio, filter=pikepdf.Name.DCTDecode)
            fd, destino = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            pdf.save(destino)
            return destino
    except Exception:
        return None


def unir_pdfs(rutas):
    """
    Un solo PDF con todas las partes, en el orden dado, sin recomprimir las imágenes.
    Devuelve la ruta de un archivo temporal que quien llama debe borrar, o None si falla.
    No escribe nada en los originales.
    """
    import os
    import tempfile
    try:
        import pikepdf
        unido = pikepdf.Pdf.new()
        abiertos = []
        try:
            for r in rutas:
                parte = pikepdf.open(r)
                abiertos.append(parte)
                unido.pages.extend(parte.pages)
            fd, destino = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            unido.save(destino)
            return destino
        finally:
            for a in abiertos:
                a.close()
    except Exception:
        return None


def declaracion_pdfa(ruta):
    """(parte, conformidad) que el archivo declara en sus metadatos, p. ej. ('2', 'B'), o None."""
    import re
    try:
        import pikepdf
        with pikepdf.open(str(ruta)) as pdf:
            xmp = bytes(pdf.Root["/Metadata"].read_bytes()).decode("utf-8", "ignore")
        parte = re.search(r"pdfaid:part(?:[^>]*>|[=\"' ]+)\s*(\d)", xmp)
        conf = re.search(r"pdfaid:conformance(?:[^>]*>|[=\"' ]+)\s*([A-Za-z])", xmp)
        return (parte.group(1), (conf.group(1).upper() if conf else "B")) if parte else None
    except Exception:
        return None


def con_descriptores(ruta, campos: dict, pdfa=None) -> bool:
    """
    Escribe en el PDF entregado SOLO los metadatos descriptivos de archivo que exige la guía de
    digitalización (título, productor, serie, subserie), nunca los de procesamiento: ni
    programa, ni equipo, ni fechas de creación de la máquina. Modifica la copia temporal que
    se le pasa; devuelve False si no pudo.
    """
    import os
    import tempfile
    try:
        import pikepdf
        permitidos = {"Title": "/Title", "Author": "/Author", "Subject": "/Subject",
                      "Keywords": "/Keywords"}
        with pikepdf.open(str(ruta)) as pdf:
            for k in list(pdf.docinfo.keys()):
                del pdf.docinfo[k]
            for clave, valor in campos.items():
                if clave in permitidos and valor:
                    pdf.docinfo[permitidos[clave]] = str(valor)[:500]
            if pdfa:
                # Solo la declaración de formato, que no es información de procesamiento: sin
                # programa, sin equipo y sin fechas de máquina. Que la declaración sea cierta
                # depende de que las partes de origen ya fueran PDF/A.
                with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as m:
                    m["pdfaid:part"] = pdfa[0]
                    m["pdfaid:conformance"] = pdfa[1]
            fd, tmp = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            pdf.save(tmp, object_stream_mode=pikepdf.ObjectStreamMode.disable)
        os.replace(tmp, str(ruta))
        return True
    except Exception:
        return False
