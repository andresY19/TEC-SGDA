"""División PDF nueva para desarrollo local, sin modificar ni borrar el origen.

Prepara todas las partes antes de publicarlas. Cada publicación usa hard-link
atómico sin reemplazo, dentro del mismo filesystem. Si este no admite enlaces,
la operación falla sin recurrir a una copia no atómica. Ante excepciones revierte
solo enlaces creados por esta llamada. No existe una transacción atómica para
todo el lote: una terminación abrupta del proceso requiere conciliación posterior.

El cargue debe conservar el origen y validar las partes antes de persistirlas.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile

import pikepdf

from geology.dominio.particion import DocumentoIlegible, _abrir_pdf, _ruta_lectura


def _limite_configurado() -> int:
    try:
        valor = int(os.environ.get("PAGINAS_POR_PARTE", "250"))
        if valor < 0:
            raise ValueError
        return valor
    except ValueError:
        raise ValueError("PAGINAS_POR_PARTE debe ser un entero no negativo.") from None


PAGINAS_POR_PARTE = _limite_configurado()
_MAX_PARTES = 100000  # Tope técnico para evitar listas/rangos descontrolados.


@dataclass(frozen=True)
class Parte:
    numero: int
    ruta: Path
    pagina_inicial: int
    pagina_final: int
    paginas: int
    tamano_bytes: int
    sha256: str


def hay_que_dividir(paginas: int) -> bool:
    if isinstance(paginas, bool) or not isinstance(paginas, int) or paginas < 0:
        raise ValueError("El número de páginas debe ser un entero no negativo.")
    return PAGINAS_POR_PARTE > 0 and paginas > PAGINAS_POR_PARTE


def _huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for trozo in iter(lambda: f.read(1048576), b""):
            h.update(trozo)
    return h.hexdigest()


def _directorio_seguro(destino: str | Path) -> Path:
    p = Path(destino)
    if ".." in p.parts or any(x.is_symlink() for x in (p, *p.parents)):
        raise ValueError("El destino no puede contener enlaces ni retrocesos.")
    p = p.resolve(strict=True)
    if not p.is_dir():
        raise ValueError("El destino debe ser un directorio existente.")
    return p


def _validar_nombres(carpeta: str, nombre: str) -> str:
    if not isinstance(carpeta, str) or not re.fullmatch(r"AC-CP-\d{5,6}", carpeta, flags=re.ASCII):
        raise ValueError("Código de carpeta no canónico.")
    if not isinstance(nombre, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", nombre) or ".." in nombre:
        raise ValueError("Nombre de archivo inseguro; utilice un nombre simple saneado.")
    raiz = nombre.split(".", 1)[0].upper()
    if raiz in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))} or nombre.endswith("."):
        raise ValueError("Nombre de archivo no portable.")
    return nombre[:-4] if nombre.lower().endswith(".pdf") else nombre


def _guardar_pdf(pdf, destino: Path) -> None:
    with destino.open("xb") as salida:
        pdf.save(salida, compress_streams=False)
        salida.flush()
        os.fsync(salida.fileno())


def _publicar_atomico(temporal: Path, destino: Path) -> None:
    # A diferencia de replace/rename en Unix, link nunca pisa un destino existente.
    os.link(temporal, destino, follow_symlinks=False)


def _sincronizar_directorio(ruta: Path) -> None:
    """Persiste entradas en plataformas POSIX; no certifica durabilidad del hardware."""
    if os.name == "nt":
        return  # Windows nativo no ofrece fsync portable de directorios.
    descriptor = os.open(ruta, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def dividir(origen: str | Path, carpeta: str, destino: str | Path,
            nombre: str) -> list[Parte]:
    """Devuelve los atributos consumidos por cargue.py; mantiene el PDF fuente."""
    fuente = _ruta_lectura(origen)
    directorio = _directorio_seguro(destino)
    base = _validar_nombres(carpeta, nombre)
    huella_original = _huella(fuente)
    publicaciones: list[tuple[Path, int, int]] = []
    try:
        with tempfile.TemporaryDirectory(prefix=".geology-division-", dir=directorio) as temporal:
            preparados = []
            with _abrir_pdf(fuente) as pdf:
                total = len(pdf.pages)
                if not hay_que_dividir(total):
                    return []
                cantidad = (total + PAGINAS_POR_PARTE - 1) // PAGINAS_POR_PARTE
                if cantidad > _MAX_PARTES:
                    raise ValueError("La división excede el límite técnico de partes.")
                destinos = [directorio / f"{carpeta}_parte_{i:05d}_{base}.pdf" for i in range(1, cantidad + 1)]
                if any(p.exists() or p.is_symlink() for p in destinos):
                    raise FileExistsError("Ya existe un destino; no se sobrescribió ningún documento.")
                for numero, inicio in enumerate(range(0, total, PAGINAS_POR_PARTE), 1):
                    fin = min(total, inicio + PAGINAS_POR_PARTE)
                    archivo = Path(temporal) / f"{numero:05d}.pdf"
                    with pikepdf.Pdf.new() as parte:
                        parte.pages.extend(pdf.pages[inicio:fin])
                        _guardar_pdf(parte, archivo)
                    with _abrir_pdf(archivo) as comprobacion:
                        if len(comprobacion.pages) != fin - inicio:
                            raise DocumentoIlegible("La parte generada no conserva el número de páginas.")
                    resultado = Parte(numero, destinos[numero - 1], inicio + 1, fin,
                                      fin - inicio, archivo.stat().st_size, _huella(archivo))
                    preparados.append((archivo, resultado))
            if _huella(fuente) != huella_original:
                raise RuntimeError("El origen cambió durante la lectura; se canceló la publicación.")
            for archivo, resultado in preparados:
                identidad = archivo.stat()
                _publicar_atomico(archivo, resultado.ruta)
                publicaciones.append((resultado.ruta, identidad.st_dev, identidad.st_ino))
            resultados = [resultado for _, resultado in preparados]
        _sincronizar_directorio(directorio)
        return resultados
    except BaseException:
        for archivo, dispositivo, inode in reversed(publicaciones):
            try:
                actual = archivo.lstat()
                if (actual.st_dev, actual.st_ino) == (dispositivo, inode):
                    archivo.unlink()
            except FileNotFoundError:
                pass
        raise


def validar_partes(partes: list[Parte], directorio: str | Path,
                   paginas_esperadas: int) -> None:
    """Comprueba continuidad, pertenencia, tamaño, SHA-256 y páginas, sin SQL.

No elimina ni repara nada. El llamador no debe crear registros si falla.
"""
    raiz = _directorio_seguro(directorio)
    if not partes or paginas_esperadas < 1:
        raise ValueError("La división no produjo una secuencia válida.")
    siguiente = 1
    rutas = set()
    for numero, parte in enumerate(partes, 1):
        ruta = _ruta_lectura(parte.ruta)
        if ruta.parent != raiz or ruta in rutas:
            raise ValueError("Una parte no pertenece al directorio de la operación o está repetida.")
        if (parte.numero != numero or parte.pagina_inicial != siguiente
                or parte.pagina_final < siguiente
                or parte.paginas != parte.pagina_final - parte.pagina_inicial + 1):
            raise ValueError("La división no conserva la secuencia de páginas.")
        if parte.tamano_bytes != ruta.stat().st_size or parte.sha256 != _huella(ruta):
            raise ValueError("Una parte no coincide con su tamaño o huella SHA-256.")
        with _abrir_pdf(ruta) as pdf:
            if len(pdf.pages) != parte.paginas:
                raise ValueError("El contenido de una parte no coincide con su rango de páginas.")
        rutas.add(ruta)
        siguiente = parte.pagina_final + 1
    if siguiente != paginas_esperadas + 1:
        raise ValueError("La división no cubre todas las páginas del original.")


def _numeros(fragmentos) -> set[int]:
    resultado = set()
    for n in fragmentos:
        if isinstance(n, bool) or not isinstance(n, int) or n < 0 or n > _MAX_PARTES:
            raise ValueError("Número de parte inválido o fuera del límite técnico.")
        resultado.add(n)
    return resultado


def faltantes(fragmentos) -> list[int]:
    """0 representa un PDF completo; solo informa huecos entre partes conocidas.

No puede detectar partes posteriores al máximo recibido: no conoce el total esperado.
"""
    numeros = _numeros(fragmentos)
    return [n for n in range(1, max(numeros, default=0) + 1) if n not in numeros]


def describir_secuencia(fragmentos) -> str:
    numeros = _numeros(fragmentos)
    if not numeros:
        return "Sin archivos."
    if numeros == {0}:
        return "Archivo completo."
    partes = ", ".join(str(n) for n in sorted(numeros - {0}))
    huecos = faltantes(numeros)
    texto = f"Partes {partes}."
    if 0 in numeros:
        texto += " También hay un archivo completo; revisar modalidad de carga."
    if huecos:
        texto += " Faltan las partes " + ", ".join(map(str, huecos)) + "."
    return texto
