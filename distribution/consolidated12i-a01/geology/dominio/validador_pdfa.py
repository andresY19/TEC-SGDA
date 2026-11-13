"""
Validación REAL de PDF/A con veraPDF, el validador de referencia del estándar (ISO 19005).

Leer los metadatos de un archivo solo dice qué DECLARA ser. Un archivo puede declarar PDF/A-2b
y no cumplirlo: pasa, por ejemplo, con imágenes en RGB sin perfil de color. veraPDF revisa
cientos de reglas del estándar y dice cuáles se incumplen. Este módulo lo ejecuta, interpreta
el resultado y, si el archivo no cumple, intenta repararlo (convertirlo a PDF/A) y vuelve a
validarlo. Lo único que se declara conforme es lo que veraPDF dio por conforme.

Si veraPDF no está instalado, el estado es NO_VALIDADO: nunca se afirma conformidad sin
haberla comprobado.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# La guía de digitalización GU-SAD-ODA-001 del Servicio Geológico pide PDF/A-1 (ISO 19005-1) para
# la copia de consulta. Por eso el perfil por defecto es 1b y se EXIGE ese perfil: un archivo en
# PDF/A-2b se convierte a PDF/A-1b. Con PDFA_PERFIL=2b se exige PDF/A-2b.
PERFIL_POR_DEFECTO = os.getenv("PDFA_PERFIL", "1b").strip().lower()
SEGUNDOS = int(os.getenv("SEGUNDOS_VERAPDF", "1800"))
CACHE = Path("deposito/pdfa")


def binario() -> str | None:
    for c in (os.getenv("VERAPDF_BIN", ""), shutil.which("verapdf") or "",
              "/opt/verapdf/verapdf", str(Path.home() / "verapdf" / "verapdf")):
        if c and Path(c).exists():
            return c
    return None


def disponible() -> bool:
    return binario() is not None


def version() -> str:
    exe = binario()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
        for linea in r.stdout.splitlines():
            if linea.lower().startswith("verapdf"):
                return linea.strip()
    except Exception:
        pass
    return "veraPDF"


def _huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for t in iter(lambda: f.read(1 << 20), b""):
            h.update(t)
    return h.hexdigest()


def validar(ruta: str | Path, perfil: str = "") -> dict:
    """
    Resultado: {validado, conforme, perfil, reglas_falladas, comprobaciones_falladas, errores:
    [{clausula, descripcion, veces}], mensaje}. Se guarda por huella del archivo: validar mil
    páginas toma un rato y el resultado solo cambia si cambia el archivo.
    """
    ruta = Path(ruta)
    exe = binario()
    if not exe:
        return {"validado": False, "conforme": False, "perfil": "", "errores": [],
                "mensaje": "veraPDF no está instalado; la conformidad PDF/A no se pudo comprobar."}
    perfil = perfil or PERFIL_POR_DEFECTO
    huella = _huella(ruta)
    f = CACHE / f"{huella}_{perfil}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        # Se fuerza el perfil exigido (-f): lo que se mide es el perfil pedido, no el que el
        # archivo diga tener.
        r = subprocess.run([exe, "-f", perfil, "--format", "mrr", str(ruta)],
                           capture_output=True, text=True, timeout=SEGUNDOS)
        raiz = ET.fromstring(r.stdout[r.stdout.index("<?xml"):])
    except subprocess.TimeoutExpired:
        return {"validado": False, "conforme": False, "perfil": perfil, "errores": [],
                "mensaje": f"La validación superó {SEGUNDOS} segundos."}
    except Exception as e:
        return {"validado": False, "conforme": False, "perfil": perfil, "errores": [],
                "mensaje": f"No se pudo interpretar el resultado de veraPDF: {type(e).__name__}"}
    informe = raiz.find(".//validationReport")
    if informe is None:
        return {"validado": False, "conforme": False, "perfil": perfil, "errores": [],
                "mensaje": "veraPDF no pudo procesar el archivo (dañado o cifrado)."}
    detalle = informe.find("details")
    errores = []
    for regla in informe.findall(".//rule"):
        if regla.get("status") == "failed":
            errores.append({
                "clausula": f"{regla.get('specification', '')} {regla.get('clause', '')}".strip(),
                "descripcion": (regla.findtext("description") or "")[:260],
                "veces": int(regla.get("failedChecks", "1"))})
    res = {
        "validado": True,
        "conforme": informe.get("isCompliant") == "true",
        "perfil": (informe.get("profileName") or "").replace(" validation profile", ""),
        "reglas_falladas": int(detalle.get("failedRules", "0")) if detalle is not None else 0,
        "comprobaciones_falladas": int(detalle.get("failedChecks", "0")) if detalle is not None else 0,
        "errores": errores[:12],
        "motor": version(),
        "mensaje": "",
    }
    res["mensaje"] = (f"Conforme con {res['perfil']} según {res['motor']}." if res["conforme"] else
                      f"No conforme con {res['perfil']}: {res['reglas_falladas']} regla(s) incumplida(s).")
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return res


def _limpiar_proceso(ruta: Path, descriptores: dict) -> None:
    """Quita del PDF/A recién convertido el programa que lo produjo y deja los descriptivos."""
    import pikepdf
    with pikepdf.open(str(ruta), allow_overwriting_input=True) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as m:
            for k in ("pdf:Producer", "xmp:CreatorTool", "pdf:Keywords"):
                if k in m:
                    del m[k]
        for k in ("/Producer", "/Creator"):
            if k in pdf.docinfo:
                del pdf.docinfo[k]
        mapa = {"Title": "/Title", "Author": "/Author", "Subject": "/Subject", "Keywords": "/Keywords"}
        for clave, valor in (descriptores or {}).items():
            if clave in mapa and valor:
                pdf.docinfo[mapa[clave]] = str(valor)[:500]
        with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as m:
            if descriptores.get("Title"):
                m["dc:title"] = str(descriptores["Title"])[:500]
            if descriptores.get("Subject"):
                m["dc:description"] = str(descriptores["Subject"])[:500]
            if descriptores.get("Keywords"):
                m["pdf:Keywords"] = str(descriptores["Keywords"])[:500]
        pdf.save(str(ruta), object_stream_mode=pikepdf.ObjectStreamMode.disable)


def convertir(origen: Path, destino: Path, descriptores: dict) -> tuple[bool, str]:
    """Conversión a PDF/A sin tocar las imágenes y sin dejar rastro del programa."""
    if not shutil.which("ocrmypdf"):
        return False, "No está instalado el motor de conversión (ocrmypdf y ghostscript)."
    try:
        tipo = "pdfa-1" if PERFIL_POR_DEFECTO.startswith("1") else "pdfa-2"
        r = subprocess.run(["ocrmypdf", "--output-type", tipo, "--skip-text", "--optimize", "0",
                            "--quiet", str(origen), str(destino)],
                           capture_output=True, text=True, timeout=SEGUNDOS)
    except subprocess.TimeoutExpired:
        return False, "La conversión a PDF/A superó el tiempo máximo."
    if not destino.exists() or destino.stat().st_size == 0:
        return False, (r.stderr or r.stdout or "la conversión no produjo archivo")[-300:]
    try:
        _limpiar_proceso(destino, descriptores)
    except Exception as e:
        return False, f"No se pudo limpiar el archivo convertido: {type(e).__name__}"
    return True, ""


def quitar_declaracion(ruta: Path) -> None:
    """Un archivo que no cumple no puede seguir diciendo que es PDF/A."""
    import pikepdf
    with pikepdf.open(str(ruta), allow_overwriting_input=True) as pdf:
        if "/Metadata" in pdf.Root:
            with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as m:
                for k in ("pdfaid:part", "pdfaid:conformance"):
                    if k in m:
                        del m[k]
        pdf.save(str(ruta))


def asegurar_pdfa(ruta: str | Path, descriptores: dict | None = None) -> dict:
    """
    Garantiza que el PDF que se entrega sea PDF/A comprobado, o dice con exactitud que no lo es.
    Modifica el archivo `ruta` (un temporal) solo si lo convierte o le quita una declaración falsa.
    Estados: CONFORME, CONFORME_TRAS_CONVERSION, NO_CONFORME, NO_VALIDADO.
    """
    ruta = Path(ruta)
    if descriptores is None:
        # Los descriptivos de archivo que ya trae el PDF se conservan en la conversión.
        try:
            import pikepdf
            with pikepdf.open(str(ruta)) as pdf:
                descriptores = {k[1:]: str(v) for k, v in pdf.docinfo.items()
                                if k in ("/Title", "/Author", "/Subject", "/Keywords")}
        except Exception:
            descriptores = {}
    v = validar(ruta)
    if not v["validado"]:
        return {"estado": "NO_VALIDADO", **v}
    if v["conforme"]:
        return {"estado": "CONFORME", **v}
    tmp = ruta.with_suffix(".pdfa.pdf")
    try:
        ok, detalle = convertir(ruta, tmp, descriptores or {})
        if ok:
            v2 = validar(tmp)
            if v2["validado"] and v2["conforme"]:
                os.replace(tmp, ruta)
                return {"estado": "CONFORME_TRAS_CONVERSION", **v2,
                        "mensaje": "Se convirtió a PDF/A sin alterar las imágenes. " + v2["mensaje"]}
            v = v2 if v2["validado"] else v
            v["mensaje"] += " La conversión automática no logró el cumplimiento."
        else:
            v["mensaje"] += f" No se pudo convertir: {detalle}"
    finally:
        Path(tmp).unlink(missing_ok=True)
    try:
        quitar_declaracion(ruta)
    except Exception:
        pass
    return {"estado": "NO_CONFORME", **v}
