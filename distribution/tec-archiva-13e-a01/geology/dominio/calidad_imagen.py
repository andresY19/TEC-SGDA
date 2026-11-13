"""
Control de calidad de la digitalización, al 100 % de las imágenes.

Criterios tomados de la Guía de digitalización GU-SAD-ODA-001 del Servicio Geológico
Colombiano y de la Memoria descriptiva del contrato: resolución mínima de 300 puntos por
pulgada, profundidad de color de escala de grises (8 bits) o color (24 bits), formato PDF/A,
texto buscable, y revisión de cada imagen frente al original en cuatro aspectos: exposición
(ni muy clara ni muy oscura), foco (sin borrosidad), alineación (sin imágenes torcidas) y
completitud. Las imágenes de baja calidad no se descartan: se documentan con el número de
página y el motivo, para que se vuelvan a capturar.

Lo que este módulo mide es una prueba automática sobre los píxeles. Sirve para encontrar las
páginas sospechosas entre cientos; no reemplaza la mirada de quien revisa contra el papel, y
por eso el informe dice «sospechosa» y no «mala».
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DPI_MINIMO = int(os.getenv("CALIDAD_DPI_MINIMO", "300"))
LADO_ANALISIS = 900                       # lado largo de la miniatura sobre la que se mide
FOCO_MINIMO = float(os.getenv("CALIDAD_FOCO_MINIMO", "25"))
INCLINACION_MAXIMA = float(os.getenv("CALIDAD_INCLINACION_GRADOS", "3"))
BLANCO_DESVIACION = 3.0                   # una página casi lisa se marca como en blanco


@dataclass
class Pagina:
    numero: int                           # consecutivo en todo el tomo, desde 1
    parte: int = 0
    dpi: int | None = None
    bits: int | None = None
    color: str = ""                       # gris, color o blanco y negro
    brillo: float | None = None
    foco: float | None = None
    inclinacion: float | None = None
    hallazgos: list[str] = field(default_factory=list)


def _imagen_de(pagina):
    """La imagen más grande de la página, o None."""
    try:
        xob = (pagina.get("/Resources") or {}).get("/XObject") or {}
        mejor, area = None, 0
        for nombre in xob.keys():
            o = xob[nombre]
            if o.get("/Subtype") == "/Image":
                a = int(o.get("/Width", 0)) * int(o.get("/Height", 0))
                if a > area:
                    mejor, area = o, a
        return mejor
    except Exception:
        return None


def _espacio_de_color(obj) -> str:
    """gris o color, según el espacio de color declarado por la imagen."""
    try:
        e = obj.get("/ColorSpace")
        if str(e) == "/DeviceRGB":
            return "color"
        if str(e) == "/DeviceGray":
            return "gris"
        if isinstance(e, list) or hasattr(e, "__len__"):
            if str(e[0]) == "/ICCBased":
                return "color" if int(e[1].get("/N", 1)) >= 3 else "gris"
            if str(e[0]) == "/Indexed":
                return "color"
    except Exception:
        pass
    return ""


def _como_gris(obj):
    """Miniatura en escala de grises de la imagen incrustada, sin cargarla entera."""
    from PIL import Image
    ancho, alto = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
    filtro = obj.get("/Filter")
    try:
        if filtro == "/DCTDecode":
            im = Image.open(io.BytesIO(obj.read_raw_bytes()))
            im.draft("L", (max(1, ancho // 3), max(1, alto // 3)))
        else:
            import pikepdf
            im = pikepdf.PdfImage(obj).as_pil_image()
        im = im.convert("L")
        im.thumbnail((LADO_ANALISIS, LADO_ANALISIS))
        return im
    except Exception:
        return None


def _inclinacion(gris) -> float | None:
    """
    Ángulo de la inclinación del texto, en grados, por perfil de proyección: se gira la
    imagen y se queda el ángulo con filas más contrastadas, que es cuando los renglones
    quedan horizontales. Solo es fiable en páginas con renglones; en fotos o planos devuelve
    algo sin sentido, y por eso es un aviso y no un error.
    """
    try:
        import cv2
        import numpy as np
        a = np.array(gris)
        _, bn = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if bn.mean() < 2:                 # casi sin tinta: no hay renglones que medir
            return None
        alto, ancho = bn.shape
        centro = (ancho / 2, alto / 2)
        mejor, puntaje = 0.0, -1.0
        for ang in np.arange(-6, 6.01, 0.5):
            m = cv2.getRotationMatrix2D(centro, float(ang), 1.0)
            r = cv2.warpAffine(bn, m, (ancho, alto), flags=cv2.INTER_NEAREST)
            p = float(np.var(r.sum(axis=1)))
            if p > puntaje:
                mejor, puntaje = float(ang), p
        return round(mejor, 1)
    except Exception:
        return None


def evaluar_pagina(numero: int, parte: int, pagina, dpi_en_pagina: int | None) -> Pagina:
    p = Pagina(numero=numero, parte=parte, dpi=dpi_en_pagina)
    obj = _imagen_de(pagina)
    if obj is None:
        p.hallazgos.append("la página no trae imagen escaneada")
        return p
    try:
        bits = int(obj.get("/BitsPerComponent", 8))
        p.bits = bits
        p.color = "blanco y negro" if bits == 1 else _espacio_de_color(obj)
    except Exception:
        pass

    if p.dpi is not None and p.dpi < DPI_MINIMO:
        p.hallazgos.append(f"resolución {p.dpi} ppp, por debajo de {DPI_MINIMO}")
    if p.bits == 1:
        p.hallazgos.append("blanco y negro puro; se exige escala de grises o color")

    gris = _como_gris(obj)
    if gris is None:
        p.hallazgos.append("no se pudo analizar la imagen")
        return p
    try:
        import cv2
        import numpy as np
        a = np.array(gris, dtype=np.uint8)
        if float(a.std()) < BLANCO_DESVIACION:
            p.brillo = round(float(a.mean()), 1)
            p.hallazgos.append("página en blanco (si es hoja de conservación, se deja)")
            return p
        p50 = float(np.percentile(a, 50))
        p5 = float(np.percentile(a, 5))
        p95 = float(np.percentile(a, 95))
        p.brillo = round(p50, 1)
        if p95 < 130:
            p.hallazgos.append("muy oscura")
        elif p5 > 200:
            p.hallazgos.append("muy clara, sin contraste")
        p.foco = round(float(cv2.Laplacian(a, cv2.CV_64F).var()), 1)
        if p.foco < FOCO_MINIMO:
            p.hallazgos.append("posible desenfoque o imagen borrosa")
        p.inclinacion = _inclinacion(gris)
        if p.inclinacion is not None and abs(p.inclinacion) > INCLINACION_MAXIMA:
            p.hallazgos.append(f"no alineada, inclinada unos {abs(p.inclinacion)} grados")
    except Exception:
        p.hallazgos.append("no se pudo medir exposición, foco y alineación")
    return p


def _es_pdfa(pdf) -> str:
    """Si el documento declara conformidad PDF/A en sus metadatos. Declara, no certifica."""
    try:
        xmp = bytes(pdf.Root["/Metadata"].read_bytes()).decode("utf-8", "ignore")
        if "pdfaid:part" in xmp:
            import re
            m = re.search(r"pdfaid:part(?:[^>]*>|[=\"' ]+)\s*(\d)", xmp)
            return f"PDF/A-{m.group(1)}" if m else "PDF/A"
    except Exception:
        pass
    return ""


def evaluar(rutas: list[Path], folios_hoja: int | None = None) -> dict:
    """Evalúa todas las páginas de las partes, en orden, y arma el informe."""
    import pikepdf
    paginas: list[Pagina] = []
    formatos: set[str] = set()
    detalle_pdfa: list[str] = []
    con_texto = 0
    total = 0
    consecutivo = 0
    for parte, ruta in enumerate(rutas, start=1):
        with pikepdf.open(str(ruta)) as pdf:
            f = _es_pdfa(pdf)
            from geology.dominio import validador_pdfa
            if validador_pdfa.disponible():
                v = validador_pdfa.validar(ruta)
                if v["validado"] and v["conforme"]:
                    formatos.add(f"{v['perfil']} verificado")
                elif v["validado"] and not f:
                    formatos.add("PDF común, no es PDF/A (la copia de entrega se convierte al generar el paquete)")
                elif v["validado"]:
                    formatos.add(f"declara PDF/A pero no cumple {v['perfil']} ({v['reglas_falladas']} reglas)")
                    detalle_pdfa.append(f"parte {parte}: " + "; ".join(
                        e["descripcion"][:110] for e in v["errores"][:2]))
                else:
                    formatos.add("PDF/A sin poder validar")
            else:
                formatos.add((f + " declarado, sin verificar") if f else "PDF sin declarar PDF/A")
            for pag in pdf.pages:
                consecutivo += 1
                total += 1
                try:
                    caja = pag.get("/MediaBox") or [0, 0, 612, 792]
                    ancho_in = abs(float(caja[2]) - float(caja[0])) / 72.0
                    img = _imagen_de(pag)
                    dpi = round(int(img.get("/Width", 0)) / ancho_in) if img is not None and ancho_in else None
                    if "/Font" in (pag.get("/Resources") or {}):
                        con_texto += 1
                except Exception:
                    dpi = None
                paginas.append(evaluar_pagina(consecutivo, parte, pag, dpi))

    sospechosas = [p for p in paginas if p.hallazgos
                   and not (len(p.hallazgos) == 1 and p.hallazgos[0].startswith("página en blanco"))]
    en_blanco = [p for p in paginas if any(h.startswith("página en blanco") for h in p.hallazgos)]
    dpis = [p.dpi for p in paginas if p.dpi]
    bits = [p.bits for p in paginas if p.bits]
    pdfa = bool(formatos) and all(f.endswith("verificado") for f in formatos)
    por_motivo: dict[str, int] = {}
    for p in sospechosas:
        for h in p.hallazgos:
            clave = h.split(",")[0].split(" (")[0]
            clave = "resolución insuficiente" if clave.startswith("resolución") else \
                    "no alineada" if clave.startswith("no alineada") else clave
            por_motivo[clave] = por_motivo.get(clave, 0) + 1

    criterios = [
        {"criterio": f"Resolución mínima {DPI_MINIMO} ppp",
         "resultado": (f"mínima {min(dpis)} ppp, media {round(sum(dpis) / len(dpis))} ppp" if dpis
                       else "no se pudo medir"),
         "cumple": bool(dpis) and min(dpis) >= DPI_MINIMO},
        {"criterio": "Escala de grises 8 bits o color 24 bits",
         "resultado": ("sin imágenes en blanco y negro puro" if bits and min(bits) > 1
                       else "hay páginas en blanco y negro puro" if bits else "no se pudo medir"),
         "cumple": bool(bits) and min(bits) > 1},
        {"criterio": "Formato PDF/A",
         "resultado": (", ".join(sorted(formatos)) or "sin datos")
                      + ((" · " + " | ".join(detalle_pdfa[:2])) if detalle_pdfa else ""),
         "cumple": pdfa},
        {"criterio": "Texto buscable (reconocimiento óptico)",
         "resultado": f"{con_texto} de {total} páginas",
         "cumple": total > 0 and con_texto == total},
        {"criterio": "Exposición, foco y alineación revisadas al 100 %",
         "resultado": (f"{len(sospechosas)} página(s) sospechosa(s) de {total}"
                       if sospechosas else f"ninguna página sospechosa de {total}"),
         "cumple": not sospechosas},
    ]
    if folios_hoja:
        criterios.append({
            "criterio": "Páginas frente a folios de la hoja de control",
            "resultado": f"{total} páginas y {folios_hoja} folios",
            "cumple": total >= folios_hoja})
    return {
        "paginas": total, "partes": len(rutas),
        "dpi_minimo": min(dpis) if dpis else None,
        "dpi_medio": round(sum(dpis) / len(dpis)) if dpis else None,
        "formato": ", ".join(sorted(formatos)),
        "criterios": criterios,
        "cumple": all(c["cumple"] for c in criterios),
        "sospechosas": [
            {"pagina": p.numero, "parte": p.parte, "dpi": p.dpi, "brillo": p.brillo,
             "foco": p.foco, "inclinacion": p.inclinacion, "motivo": "; ".join(p.hallazgos)}
            for p in sospechosas],
        "en_blanco": [p.numero for p in en_blanco],
        "por_motivo": por_motivo,
        "nota": ("Prueba automática sobre los píxeles de cada imagen. Señala páginas "
                 "sospechosas para que se contrasten con el original; no reemplaza la "
                 "revisión visual. Las páginas sospechosas se documentan con su número y "
                 "motivo para volver a capturarlas, no se descartan."),
    }


def informe_en_cache(carpeta: str, rutas: list[Path], folios_hoja: int | None,
                     carpeta_cache: Path = Path("deposito/calidad")) -> dict:
    """
    El informe se guarda al lado del almacén: medir mil páginas toma un rato y el resultado
    solo cambia si cambian los archivos. La llave es el tamaño y la fecha de cada parte.
    """
    llave = [[str(r), r.stat().st_size, int(r.stat().st_mtime)] for r in rutas] + [folios_hoja]
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    f = carpeta_cache / f"{carpeta}.json"
    if f.exists():
        try:
            guardado = json.loads(f.read_text(encoding="utf-8"))
            if guardado.get("llave") == llave:
                return guardado["informe"]
        except Exception:
            pass
    informe = evaluar(rutas, folios_hoja)
    try:
        f.write_text(json.dumps({"llave": llave, "informe": informe}, ensure_ascii=False),
                     encoding="utf-8")
    except Exception:
        pass
    return informe


def informe_en_excel(carpeta: str, informe: dict) -> bytes:
    """Informe de control de calidad para entregar: resumen y detalle por página."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    ws.append([f"Control de calidad de la digitalización · {carpeta}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["Criterio", "Resultado", "Cumple"])
    for c in ws[3]:
        c.font = Font(bold=True)
    for c in informe["criterios"]:
        ws.append([c["criterio"], c["resultado"], "Sí" if c["cumple"] else "No"])
    ws.append([])
    ws.append(["Nota", informe["nota"]])
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 10
    d = wb.create_sheet("Páginas sospechosas")
    d.append(["Página (folio de imagen)", "Parte", "Resolución ppp", "Brillo", "Foco",
              "Inclinación °", "Motivo"])
    for c in d[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8DFC9")
    for s in informe["sospechosas"]:
        d.append([s["pagina"], s["parte"], s["dpi"], s["brillo"], s["foco"],
                  s["inclinacion"], s["motivo"]])
    for col, w in zip("ABCDEFG", (22, 8, 15, 9, 9, 13, 70)):
        d.column_dimensions[col].width = w
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
