"""Infraestructura SQLAlchemy 2 nueva, destinada al desarrollo local.

No carga .env ni modelos, abre conexiones o ejecuta DDL al importar.
El llamador debe proporcionar el entorno. crear_tablas exige modelos completos
y autorización manual local además de GEOLOGY_PERMITIR_DDL=1; nunca aplica estructura.py.
"""
from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, configure_mappers, sessionmaker

_log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Único registro declarativo compartido por los modelos de GEOLOGY."""


def _entero(nombre: str, defecto: int, minimo: int) -> int:
    try:
        valor = int(os.environ.get(nombre, str(defecto)))
        if valor < minimo:
            raise ValueError
        return valor
    except (TypeError, ValueError):
        raise RuntimeError(f"Configuración numérica inválida: {nombre}.") from None


def _crear_motor():
    try:
        url = make_url(os.environ.get("DATABASE_URL", ""))
        if url.get_backend_name() != "postgresql":
            raise ValueError
        if url.drivername not in ("postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
            raise ValueError
        if not url.host or not url.database or not url.username or not url.password:
            raise ValueError
        if "<" in url.password or ">" in url.password:
            raise ValueError
    except Exception:
        raise RuntimeError("DATABASE_URL debe definir una conexión PostgreSQL completa y operativa.") from None
    opciones = dict(
        pool_pre_ping=True,
        pool_size=_entero("DB_POOL_SIZE", 10, 1),
        max_overflow=_entero("DB_MAX_OVERFLOW", 20, 0),
        pool_timeout=_entero("DB_POOL_TIMEOUT", 30, 1),
        connect_args={"connect_timeout": _entero("DB_CONNECT_TIMEOUT", 5, 1)},
        echo=False,
        hide_parameters=True,
    )
    try:
        # create_engine configura el pool; no abre una conexión DBAPI.
        return create_engine(url, **opciones)
    except Exception:
        raise RuntimeError("No se pudo configurar el motor PostgreSQL; revise controlador y configuración.") from None


motor = _crear_motor()
SesionLocal = sessionmaker(bind=motor, class_=Session, autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    """La ruta decide los commits; esta dependencia revierte errores y cierra siempre."""
    sesion = SesionLocal()
    try:
        yield sesion
    except BaseException:
        try:
            sesion.rollback()
        except Exception:
            _log.warning("No se pudo revertir la sesión de base de datos.")
        raise
    finally:
        sesion.close()


MODULOS_MODELOS = (
    "valoracion", "unidad", "bitacora", "consumo_lector", "deposito", "caja",
    "seguimiento", "contrato", "vigilancia", "cuenta",
)
CLASES_MODELOS = (
    "Fondo", "Periodo", "Seccion", "Serie", "Subserie", "Expediente", "Tramite",
    "UnidadInventario", "Trazabilidad", "ConsumoModelo", "Archivo", "Caja",
    "Asignacion", "HitoCronograma", "DocumentoContrato", "ItemEliminacion",
    "LoteContrato", "ObligacionContrato", "ObservacionSupervision", "PagoContrato",
    "ParametroContrato", "ProcesoEliminacion", "Alerta", "DescargaRegistro",
    "DocumentoApoyo", "SesionEdicion", "UsuarioBD",
)


def registrar_modelos() -> None:
    """Registro explícito y completo; no inspecciona ni modifica la base de datos."""
    carpeta = Path(__file__).resolve().parents[1] / "modelos"
    faltantes = [nombre for nombre in MODULOS_MODELOS if not (carpeta / f"{nombre}.py").is_file()]
    if faltantes:
        raise RuntimeError("Registro de modelos incompleto; faltan: " + ", ".join(faltantes) + ".")
    try:
        modelos = importlib.import_module("geology.modelos")
        for nombre in CLASES_MODELOS:
            clase = getattr(modelos, nombre)
            if not isinstance(clase, type) or not issubclass(clase, Base):
                raise TypeError
            mapeador = inspect(clase)
            if mapeador.local_table.metadata is not Base.metadata:
                raise ValueError
        configure_mappers()
        # Fuerza la resolución local de FK antes de permitir una conexión DDL.
        list(Base.metadata.sorted_tables)
    except Exception:
        raise RuntimeError("No se pudo validar el registro completo de modelos ORM.") from None


def _autorizar_ddl_local(autorizacion_local: bool) -> None:
    """Guardia manual: una variable sola no autoriza DDL, tampoco en producción."""
    if autorizacion_local is not True or os.environ.get("GEOLOGY_PERMITIR_DDL", "") != "1":
        raise RuntimeError("DDL deshabilitado; requiere llamada manual autorizada exclusivamente local.")
    if os.environ.get("GEOLOGY_ENTORNO", "").strip().lower() not in {
        "local", "desarrollo", "development", "test", "testing", "pruebas",
    }:
        raise RuntimeError("DDL no autorizado fuera de un entorno local explícito.")


def crear_tablas(*, autorizacion_local: bool = False) -> None:
    """Operación manual separada del arranque; no sustituye migraciones revisadas."""
    _autorizar_ddl_local(autorizacion_local)
    registrar_modelos()
    try:
        Base.metadata.create_all(bind=motor)
    except Exception:
        raise RuntimeError("No se pudieron crear las tablas de GEOLOGY.") from None


def verificar_conexion() -> bool:
    """Única comprobación explícita: SELECT 1, sin cambios de esquema ni datos."""
    try:
        with motor.connect() as conexion:
            return conexion.execute(text("SELECT 1")).scalar_one() == 1
    except Exception:
        _log.warning("No se pudo verificar la conexión de base de datos.")
        return False
