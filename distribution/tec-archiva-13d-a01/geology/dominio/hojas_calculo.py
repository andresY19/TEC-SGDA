"""Exportación tabular ISAD(G) nueva para desarrollo local, sin acceso a BD.

Contrato observado: filas de diccionarios y columnas (numeral, etiqueta).
La primera fila contiene numerales y la segunda etiquetas. No sustituye la
plantilla oficial de base_isadg.py ni certifica el aspecto del formato original.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
import io
import math

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


def _escribir(hoja, fila: int, columna: int, valor) -> None:
    if isinstance(valor, str):
        if len(valor) > 32767 or ILLEGAL_CHARACTERS_RE.search(valor):
            raise ValueError("Una celda contiene texto no representable sin pérdida en XLSX.")
        celda = hoja.cell(fila, columna, valor)
        # Fuerza texto literal incluso para =, +, -, @, espacios o tabuladores iniciales.
        # No altera el valor mediante apóstrofos ni permite que se serialice como fórmula.
        celda.data_type = "s"
    elif valor is None:
        hoja.cell(fila, columna)
    elif isinstance(valor, (bool, int, float, Decimal, date, datetime, time)):
        if isinstance(valor, (float, Decimal)) and not math.isfinite(valor):
            raise ValueError("Una celda numérica no es finita.")
        if isinstance(valor, (datetime, time)) and valor.tzinfo is not None:
            raise ValueError("Las fechas Excel deben carecer de zona horaria explícita.")
        hoja.cell(fila, columna, valor)
    else:
        raise TypeError("Tipo de celda no admitido por la exportación tabular.")


def generar_base_isadg(filas, columnas) -> bytes:
    columnas = list(columnas)
    if not columnas or len(columnas) > 16384:
        raise ValueError("Número de columnas fuera de los límites XLSX.")
    if any(not isinstance(c, (tuple, list)) or len(c) != 2 or not all(isinstance(v, str) for v in c) or not c[1] for c in columnas):
        raise ValueError("Cada columna debe contener un numeral y una etiqueta textual.")
    libro = Workbook()
    try:
        hoja = libro.active
        hoja.title = "Base ISADG"
        hoja.freeze_panes = "A3"
        for i, (numeral, etiqueta) in enumerate(columnas, 1):
            _escribir(hoja, 1, i, numeral)
            _escribir(hoja, 2, i, etiqueta)
        for n, registro in enumerate(filas, 3):
            if n > 1048576:
                raise ValueError("Número de filas fuera de los límites XLSX.")
            if not isinstance(registro, Mapping):
                raise TypeError("Cada fila debe ser un diccionario o mapping.")
            for i, (_, etiqueta) in enumerate(columnas, 1):
                _escribir(hoja, n, i, registro.get(etiqueta))
        salida = io.BytesIO()
        libro.save(salida)
        return salida.getvalue()
    finally:
        libro.close()
