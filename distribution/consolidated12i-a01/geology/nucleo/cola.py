"""Aplicación Celery nueva para desarrollo local, sin consumo durante imports.

El worker futuro registra geology.trabajos mediante include. Las pruebas y otros
llamadores pueden solicitar registrar_tareas() explícitamente sin iniciar workers.
No carga .env, no usa configuración de producción y no crea tareas periódicas.
"""
from __future__ import annotations

import importlib
import os
import re
from urllib.parse import urlsplit

from celery import Celery
from kombu import Exchange, Queue


def _redis(nombre: str) -> str:
    valor = os.environ.get(nombre, "")
    try:
        url = urlsplit(valor)
        if url.scheme not in ("redis", "rediss") or not url.hostname or url.port == 0:
            raise ValueError
        if not re.fullmatch(r"/\d+", url.path) or url.query or url.fragment:
            raise ValueError
    except Exception:
        raise RuntimeError(f"Configuración Redis inválida: {nombre}.") from None
    return valor


_proyecto = os.environ.get("GEOLOGY_LOCAL_PROJECT", "")
_cola = os.environ.get("GEOLOGY_COLA", "")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", _proyecto):
    raise RuntimeError("GEOLOGY_LOCAL_PROJECT debe identificar un proyecto local independiente.")
if not _cola.startswith(_proyecto + "-") or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,149}", _cola):
    raise RuntimeError("GEOLOGY_COLA debe ser exclusiva y comenzar con GEOLOGY_LOCAL_PROJECT seguido de guion.")
if os.environ.get("GEOLOGY_ENTORNO", "desarrollo").strip().lower() not in (
    "desarrollo", "development", "local", "test", "testing", "pruebas",
):
    raise RuntimeError("Esta implementación de Celery está limitada al desarrollo local.")

MODULOS_TAREAS = ("geology.trabajos",)
NOMBRES_TAREAS = (
    "geology.levantar_hoja", "geology.preparar_digitalizacion", "geology.ping",
)
celery_app = Celery(
    "geology_local", broker=_redis("CELERY_BROKER_URL"),
    backend=_redis("CELERY_RESULT_BACKEND"), include=MODULOS_TAREAS,
    set_as_current=False,
)
celery_app.conf.update(
    task_default_queue=_cola,
    task_default_exchange=_cola,
    task_default_exchange_type="direct",
    task_default_routing_key=_cola,
    task_queues=(Queue(_cola, Exchange(_cola, type="direct"), routing_key=_cola),),
    task_routes={nombre: {"queue": _cola, "routing_key": _cola} for nombre in NOMBRES_TAREAS},
    task_create_missing_queues=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_accept_content=["json"],
    task_always_eager=False,
    timezone=os.environ.get("ZONA_HORARIA", "America/Bogota"),
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=5,
    broker_transport_options={"global_keyprefix": _proyecto + ":"},
    result_backend_transport_options={"global_keyprefix": _proyecto + ":"},
    worker_enable_remote_control=False,
    beat_schedule={},
)


def registrar_tareas() -> tuple[str, ...]:
    """Importa las tareas reales y verifica sus nombres; no las invoca ni encola."""
    try:
        for modulo in MODULOS_TAREAS:
            importlib.import_module(modulo)
        celery_app.finalize()
        if any(nombre not in celery_app.tasks for nombre in NOMBRES_TAREAS):
            raise ValueError
    except Exception:
        raise RuntimeError("No se pudieron registrar las tareas locales de GEOLOGY.") from None
    return NOMBRES_TAREAS
