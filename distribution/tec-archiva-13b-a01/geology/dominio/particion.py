"""Bloques PDF nuevos para desarrollo local; no reconstrucción certificada.

Lee el original sin escribirlo. No admite PDF cifrados, tampoco con clave vacía.
El límite de bytes se aplica al PDF binario antes de base64. Cada bloque se
serializa con una salida acotada: nunca se entrega una página que exceda el tope.
La memoria del analizador PDF y de los objetos de una página no tiene un límite
duro; PDF no confiables requieren además límites del proceso/contenedor.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import io
import math
from pathlib import Path
from typing import Iterator

import pikepdf


class DocumentoIlegible(ValueError):
    """No es posible leer el documento dentro de las condiciones solicitadas."""


@dataclass(frozen=True)
class Bloque:
    numero: int
    pagina_inicial: int
    pagina_final: int
    contenido: bytes


def _ruta_lectura(ruta: str | Path) -> Path:
    p = Path(ruta)
    if ".." in p.parts or any(x.is_symlink() for x in (p, *p.parents)):
        raise DocumentoIlegible("La ruta del documento no puede contener enlaces ni retrocesos.")
    try:
        p = p.resolve(strict=True)
        if not p.is_file():
            raise OSError
    except OSError:
        raise DocumentoIlegible("El documento no es un archivo regular disponible.") from None
    return p


@contextmanager
def _abrir_pdf(ruta: str | Path):
    p = _ruta_lectura(ruta)
    try:
        pdf = pikepdf.open(p, attempt_recovery=False, access_mode=pikepdf.AccessMode.stream)
    except pikepdf.PasswordError:
        raise DocumentoIlegible("El PDF está cifrado; se requiere una copia autorizada sin cifrado.") from None
    except (pikepdf.PdfError, OSError, RuntimeError, ValueError):
        raise DocumentoIlegible("No se pudo abrir un PDF válido; no se intentó repararlo.") from None
    try:
        if pdf.is_encrypted:
            raise DocumentoIlegible("El PDF está cifrado; no se procesan documentos cifrados.")
        if not len(pdf.pages):
            raise DocumentoIlegible("El PDF no contiene páginas.")
        yield pdf
    finally:
        pdf.close()


def contar_paginas(ruta: str | Path) -> int:
    try:
        with _abrir_pdf(ruta) as pdf:
            return len(pdf.pages)
    except (pikepdf.PdfError, OSError, RuntimeError):
        raise DocumentoIlegible("No se pudieron contar las páginas del PDF.") from None


class _ExcedeLimite(Exception):
    pass


class _SalidaAcotada(io.BytesIO):
    def __init__(self, limite: int):
        super().__init__()
        self.limite = limite

    def write(self, datos):
        if self.tell() + len(datos) > self.limite:
            raise _ExcedeLimite
        return super().write(datos)


def _serializar(pdf, limite: int) -> bytes:
    with _SalidaAcotada(limite) as salida:
        pdf.save(salida, compress_streams=False)
        return salida.getvalue()


def bloques(ruta: str | Path, tope_paginas: int, tope_mb: float,
            avisos: list[str]) -> Iterator[Bloque]:
    """Iterador de PDFs consecutivos; MB significa 1.048.576 bytes.

Conserva un bloque aceptado y un candidato acotado, no el PDF completo en bytes.
El consumidor debe cerrar el iterador si abandona la lectura anticipadamente.
"""
    if isinstance(tope_paginas, bool) or not isinstance(tope_paginas, int) or tope_paginas < 1:
        raise ValueError("El límite de páginas debe ser un entero positivo.")
    try:
        valido = (not isinstance(tope_mb, bool) and isinstance(tope_mb, (int, float))
                  and math.isfinite(tope_mb) and tope_mb > 0
                  and math.isfinite(tope_mb * 1048576))
    except OverflowError:
        valido = False
    if not valido:
        raise ValueError("El límite de tamaño debe ser finito y positivo.")
    limite = int(tope_mb * 1048576)
    if limite < 1:
        raise ValueError("El límite debe permitir al menos un byte.")
    if not isinstance(avisos, list):
        raise TypeError("avisos debe ser una lista.")

    def recorrer():
        try:
            with _abrir_pdf(ruta) as origen:
                indice, numero = 0, 1
                while indice < len(origen.pages):
                    inicio, aceptado = indice, None
                    with pikepdf.Pdf.new() as parte:
                        while indice < len(origen.pages) and indice - inicio < tope_paginas:
                            parte.pages.append(origen.pages[indice])
                            try:
                                contenido = _serializar(parte, limite)
                            except _ExcedeLimite:
                                if aceptado is None:
                                    mensaje = f"La página {indice + 1} excede el límite binario del lector."
                                    avisos.append(mensaje)
                                    raise DocumentoIlegible(mensaje) from None
                                break
                            aceptado = contenido
                            indice += 1
                    yield Bloque(numero, inicio + 1, indice, aceptado)
                    numero += 1
        except DocumentoIlegible:
            raise
        except (pikepdf.PdfError, OSError, RuntimeError, ValueError):
            raise DocumentoIlegible("La lectura del PDF se interrumpió; el original se conserva.") from None

    return recorrer()
