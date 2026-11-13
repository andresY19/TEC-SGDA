"""Conversión local verificable; no equivale a una aprobación archivística.

Cada intento conserva sus intermedios. Los eventos exclusivos del diario permiten
conciliar un commit cuyo resultado sea desconocido sin eliminar evidencia.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unicodedata
import uuid
import xml.etree.ElementTree as ET


class ErrorPDFa(RuntimeError):
    pass


def perfil_efectivo(perfil: str | None) -> str:
    # El procesamiento histórico usa OCRmyPDF «pdfa», cuyo perfil efectivo es 2b.
    # No se cambia PDFA_PERFIL, utilizado por otros consumidores.
    if perfil is None:
        return "2b"
    if not isinstance(perfil, str) or perfil not in ("1b", "2b"):
        raise ErrorPDFa("Perfil no admitido; use 1b o 2b.")
    return perfil


def huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with Path(ruta).open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def evento(base: Path, estado: str, **datos) -> Path:
    ruta = base / f"evento-{uuid.uuid4().hex}.json"
    with ruta.open("x", encoding="utf-8") as f:
        json.dump({"estado": estado, **datos}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    return ruta


def _ejecutar(args: list[str], segundos: int) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=segundos)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ErrorPDFa(f"No se pudo ejecutar {Path(args[0]).name}: {type(exc).__name__}") from None
    if r.returncode:
        # No propagar stderr: puede contener información del documento o entorno.
        raise ErrorPDFa(f"Falló {Path(args[0]).name} (código {r.returncode}).")
    return r.stdout


def validar(ruta: Path, perfil: str, *, informe: Path | None = None) -> dict:
    perfil_efectivo(perfil)
    from geology.dominio.validador_pdfa import binario
    exe = binario()
    if not exe:
        raise ErrorPDFa("veraPDF no está disponible; conformidad no comprobada.")
    salida = _ejecutar([exe, "-f", perfil, "--format", "mrr", str(ruta)], 1800)
    if informe is not None:
        with informe.open("x", encoding="utf-8", newline="") as f:
            f.write(salida)
            f.flush()
            os.fsync(f.fileno())
    try:
        raiz = ET.fromstring(salida[salida.index("<?xml"):])
        informes = raiz.findall(".//validationReport")
        if len(informes) != 1:
            raise ValueError()
        validacion = informes[0]
        detalle = validacion.find("details")
        nombre = validacion.get("profileName", "")
        if (validacion.get("isCompliant") != "true" or f"PDF/A-{perfil}" not in nombre
                or detalle is None or int(detalle.get("failedRules", "-1")) != 0
                or int(detalle.get("failedChecks", "-1")) != 0):
            raise ValueError()
    except (ValueError, ET.ParseError):
        raise ErrorPDFa("veraPDF no certificó el perfil solicitado.") from None
    return {"conforme": True, "perfil": perfil, "perfil_verapdf": nombre,
            "reglas_falladas": 0, "comprobaciones_falladas": 0,
            "informe": str(informe) if informe else None,
            "archivo_validado_sha256": huella(ruta),
            "informe_sha256": hashlib.sha256(salida.encode()).hexdigest()}


def verificar_diario(ruta_evento: Path) -> dict:
    """Lee sin modificar diarios nuevos o históricos de validado_publicado.

    El defecto 10A devolvía un Element XML en «informe». La recuperación sólo
    admite el XML adyacente conocido, con sus hashes y perfil comprobados; no
    busca por nombres ni corrige el diario histórico. Un informe ausente o
    inconsistente queda pendiente de revisión, nunca aprobado por suposición.
    """
    ruta_evento = Path(ruta_evento)
    try:
        datos = json.loads(ruta_evento.read_text(encoding="utf-8"))
        if datos.get("estado") != "validado_publicado":
            raise ValueError()
        perfil = perfil_efectivo(datos["perfil"])
        xml = ruta_evento.parent / "verapdf.xml"
        declarado = datos.get("informe")
        legado = isinstance(declarado, str) and declarado.startswith("<Element 'validationReport'")
        if not legado and (not declarado or Path(declarado).resolve() != xml.resolve()):
            raise ValueError()
        if huella(xml) != datos["informe_sha256"]:
            raise ValueError()
        pdf = Path(datos["ruta"])
        sha = huella(pdf)
        if sha != datos["sha256"] or datos.get("archivo_validado_sha256", sha) != sha:
            raise ValueError()
        contenido_xml = xml.read_text(encoding="utf-8")
        raiz = ET.fromstring(contenido_xml[contenido_xml.index("<?xml"):])
        informes = raiz.findall(".//validationReport")
        if len(informes) != 1:
            raise ValueError()
        validacion = informes[0]
        detalle = validacion.find("details")
        if (validacion.get("isCompliant") != "true"
                or f"PDF/A-{perfil}" not in validacion.get("profileName", "")
                or detalle is None or int(detalle.get("failedRules", "-1")) != 0
                or int(detalle.get("failedChecks", "-1")) != 0):
            raise ValueError()
        return {"verificado": True, "informe": str(xml), "informe_sha256": huella(xml),
                "ruta": str(pdf), "sha256": sha, "perfil": perfil,
                "referencia_historica_recuperada": legado, "diario_modificado": False}
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
        raise ErrorPDFa("Diario no verificable; requiere revisión sin modificar evidencia.") from None


def contenido(ruta: Path) -> list[str]:
    """Texto normalizado por página: verifica continuidad y orden del texto existente."""
    import pikepdf
    from pdfminer.high_level import extract_text
    try:
        with pikepdf.open(ruta) as pdf:
            if pdf.is_encrypted or not len(pdf.pages):
                raise ValueError()
            n = len(pdf.pages)
        return ["".join(unicodedata.normalize("NFC", extract_text(
            str(ruta), page_numbers=[i])).split()) for i in range(n)]
    except Exception:
        raise ErrorPDFa("PDF ilegible, cifrado o sin páginas.") from None


def convertir(origen: Path, destino: Path, *, perfil: str | None = None,
              consulta: bool = False, con_ocr: bool = True) -> dict:
    efectivo = perfil_efectivo(perfil)
    origen, destino = Path(origen), Path(destino)
    if destino.exists() or destino.is_symlink() or origen.resolve() == destino.resolve():
        raise ErrorPDFa("El destino debe ser nuevo y diferente del original.")
    sha = huella(origen)
    paginas = contenido(origen)
    # Reserva basada en raster A4 RGB 300dpi (aprox. 26 MiB/página), dos copias
    # de trabajo, más original/salida. Es una cota de admisión, no una cuota.
    reserva = len(paginas) * 2 * 26 * 1024**2 + origen.stat().st_size * 4
    existente = destino.parent
    while not existente.exists():
        existente = existente.parent
    if shutil.disk_usage(existente).free < reserva:
        raise ErrorPDFa("Espacio insuficiente para la reserva de procesamiento.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    intento = destino.parent / f".pdfa-{uuid.uuid4().hex}"
    intento.mkdir(exist_ok=False)
    temporal = intento / "resultado.pdf"
    evento(intento, "iniciado", origen_sha256=sha, perfil_solicitado=perfil,
           perfil_efectivo=efectivo, reserva_bytes=reserva)
    try:
        tipo = "pdfa" if perfil is None else {"1b": "pdfa-1", "2b": "pdfa-2"}[perfil]
        args = ["ocrmypdf", "--output-type", tipo, "--skip-text", "--quiet"]
        if consulta:
            args += ["--deskew", "--clean-final", "--rotate-pages"]
            if con_ocr:
                args += ["-l", os.getenv("IDIOMA_OCR", "spa"), "--sidecar",
                         str(temporal.with_suffix(".txt"))]
            else:
                args += ["--tesseract-timeout", "0"]
        else:
            args += ["--optimize", "0"]
        _ejecutar(args + [str(origen), str(temporal)], 1800)
        resultado = validar(temporal, efectivo, informe=intento / "verapdf.xml")
        despues = contenido(temporal)
        if len(paginas) != len(despues) or any(a and a != b for a, b in zip(paginas, despues)):
            raise ErrorPDFa("Cambió la cantidad, el orden o el texto de las páginas.")
        if huella(origen) != sha:
            raise ErrorPDFa("El original cambió durante el procesamiento.")
        sha_salida = huella(temporal)
        with temporal.open("rb") as f:
            os.fsync(f.fileno())
        # link publica sin sobrescritura; si no se admite, falla conservando evidencia.
        os.link(temporal, destino)
        texto = temporal.with_suffix(".txt")
        resultado.update(ruta=str(destino), sha256=sha_salida, origen_sha256=sha,
                         paginas=len(paginas), perfil_solicitado=perfil,
                         ruta_texto=str(texto) if texto.is_file() else None,
                         texto_por_pagina_verificado=True)
        if texto.is_file():
            resultado["texto_sha256"] = huella(texto)
        evento(intento, "validado_publicado", **resultado)
        return resultado
    except BaseException as exc:
        evento(intento, "fallido_requiere_revision", error=type(exc).__name__)
        raise


def preparar(archivo_id: int, sesiones, *, perfil: str | None = None) -> dict:
    """Publica referencias SQL sólo cuando ambos derivados están verificados.

    No hay atomicidad PostgreSQL/filesystem. Un commit incierto conserva todos
    los archivos y deja un evento previo que exige conciliación manual.
    """
    efectivo = perfil_efectivo(perfil)  # Antes de abrir sesión o escribir.
    from geology.modelos import Archivo
    from datetime import datetime
    db = sesiones()
    try:
        a = db.get(Archivo, archivo_id)
        if a is None:
            raise ErrorPDFa("El archivo no existe.")
        campos = ("ruta", "ruta_matriz", "ruta_consulta", "ruta_texto")
        previo = {k: getattr(a, k) for k in campos}
        sha_registrado = getattr(a, "sha256", None)
        nombre, con_ocr = a.nombre_original, not a.tiene_capa_de_texto
    finally:
        db.close()
    origen = Path(previo["ruta"])
    sha = huella(origen)
    if sha_registrado and sha != sha_registrado:
        raise ErrorPDFa("La huella del original no coincide con la registrada.")
    base = origen.parent / "preservacion" / "versiones" / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=False)
    evento(base, "iniciado", archivo_id=archivo_id, origen_sha256=sha,
           referencias_previas=previo, perfil_solicitado=perfil, perfil_efectivo=efectivo)
    try:
        matriz = convertir(origen, base / "matriz.pdf", perfil=perfil)
        consulta = convertir(origen, base / "consulta.pdf", perfil=perfil,
                             consulta=True, con_ocr=con_ocr)
        if huella(origen) != sha:
            raise ErrorPDFa("El original cambió durante la operación.")
        db = sesiones()
        try:
            a = db.get(Archivo, archivo_id, with_for_update=True)
            if (a is None or any(getattr(a, k) != v for k, v in previo.items())
                    or getattr(a, "sha256", None) != sha_registrado):
                raise ErrorPDFa("Las referencias cambiaron; requiere conciliación.")
            if huella(origen) != sha:
                raise ErrorPDFa("El original cambió antes del commit.")
            for r in (matriz, consulta):
                if huella(Path(r["ruta"])) != r["sha256"]:
                    raise ErrorPDFa("Cambió un derivado antes del commit.")
            a.ruta_matriz, a.ruta_consulta = matriz["ruta"], consulta["ruta"]
            a.ruta_texto = consulta["ruta_texto"]
            a.procesado_en, a.error_proceso = datetime.now(), None
            evento(base, "commit_pendiente_conciliar_si_interrumpido", archivo_id=archivo_id,
                   matriz=matriz, consulta=consulta)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
        evento(base, "sql_confirmado", archivo_id=archivo_id, matriz=matriz, consulta=consulta)
        return {"archivo": nombre, "matriz": matriz["ruta"], "consulta": consulta["ruta"],
                "problemas": [], "perfil": efectivo, "perfil_solicitado": perfil,
                "manifiesto": str(base), "resultados": [matriz, consulta]}
    except BaseException as exc:
        evento(base, "no_confirmado_requiere_conciliacion", error=type(exc).__name__)
        raise
