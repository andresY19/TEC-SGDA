"""
Punto de entrada de GEOLOGY.

Ejecución local:
    uvicorn geology.main:aplicacion --reload
Documentación interactiva (solo en desarrollo):
    http://localhost:8080/docs
"""
from __future__ import annotations

import re
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from geology.nucleo.ajustes import configuracion
from geology.nucleo.bd import registrar_modelos, verificar_conexion
from geology.nucleo.cola import celery_app

# La documentación interactiva es un mapa completo de la interfaz de programación. Se
# publica solo en desarrollo; en producción responde 404.
_publica = not configuracion.es_produccion

@asynccontextmanager
async def ciclo_de_vida(app):
    """Solo configuración y metadata en memoria. Sin I/O de infraestructura ni DDL."""
    from geology.nucleo.pases import llave_configurada
    app.state.configuracion_validada = False
    if not llave_configurada():
        raise RuntimeError("Sesiones no configuradas: se requiere una clave local válida.")
    registrar_modelos()
    app.state.configuracion_validada = True
    try:
        yield
    finally:
        app.state.configuracion_validada = False


aplicacion = FastAPI(
    lifespan=ciclo_de_vida,
    title=configuracion.NOMBRE,
    description=configuracion.DESCRIPCION,
    version=configuracion.VERSION,
    docs_url="/docs" if _publica else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _publica else None,
)


@aplicacion.middleware("http")
async def cabeceras_de_proteccion(peticion, siguiente):
    respuesta = await siguiente(peticion)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["ngrok-skip-browser-warning"] = "true"
    if configuracion.es_produccion:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    return respuesta


def _anotar_descarga(peticion, respuesta, inline: bool) -> None:
    """Escribe en el registro quién descargó qué. Nunca debe romper la descarga."""
    from geology.dominio import vigilancia as vg
    from geology.modelos import UsuarioBD
    from geology.nucleo.bd import SesionLocal
    from geology.nucleo.pases import leer_pase
    cab = peticion.headers.get("authorization", "")
    pase = cab[7:].strip() if cab.lower().startswith("bearer ") else ""
    correo = leer_pase(pase) if pase else None
    if not correo:
        return
    db = SesionLocal()
    try:
        u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo).first()
        if not u or not u.activo:
            return
        from geology.nucleo.sesiones import validar
        if not validar(pase, u.clave_hash):
            return
        archivo = ""
        m = re.search(r'filename="?([^";]+)', respuesta.headers.get("content-disposition", ""))
        if m:
            archivo = m.group(1)
        tamano = respuesta.headers.get("content-length")
        ip = (peticion.headers.get("x-forwarded-for", "").split(",")[0].strip()
              or (peticion.client.host if peticion.client else ""))
        vg.registrar_descarga(db, u, peticion.url.path, peticion.url.query, archivo,
                              int(tamano) if tamano and tamano.isdigit() else None, ip, inline=inline)
    finally:
        db.close()


@aplicacion.middleware("http")
async def registro_de_descargas(peticion, siguiente):
    respuesta = await siguiente(peticion)
    try:
        if respuesta.status_code == 200 and peticion.method in ("GET", "POST"):
            disp = respuesta.headers.get("content-disposition", "").lower()
            ruta = peticion.url.path
            vista_de_la_entidad = "inline" in disp and ruta.startswith("/consulta")
            if "attachment" in disp or vista_de_la_entidad:
                await run_in_threadpool(_anotar_descarga, peticion, respuesta, vista_de_la_entidad)
    except Exception:       # el registro nunca debe impedir una descarga
        pass
    return respuesta


aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from geology.rutas import (apoyo, cargue, consulta, contrato, cuentas, entrega, instrumentos, planeacion,  # noqa: E402
                           seguimiento, ubicacion, unidades, vigilancia)

aplicacion.include_router(cuentas.router)
aplicacion.include_router(unidades.router)
aplicacion.include_router(cargue.router)
aplicacion.include_router(ubicacion.router)
aplicacion.include_router(instrumentos.router)
aplicacion.include_router(planeacion.router)
aplicacion.include_router(consulta.router)
aplicacion.include_router(entrega.router)
aplicacion.include_router(seguimiento.router)
aplicacion.include_router(contrato.router)
aplicacion.include_router(apoyo.router)
aplicacion.include_router(vigilancia.router)

# La interfaz se sirve desde el mismo servidor.
INTERFAZ = Path(__file__).parent / "interfaz"
if INTERFAZ.exists():
    aplicacion.mount("/recursos", StaticFiles(directory=INTERFAZ), name="recursos")

    @aplicacion.get("/app", include_in_schema=False)
    def interfaz():
        return FileResponse(INTERFAZ / "index.html")

    @aplicacion.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/app")


@aplicacion.get("/estado", tags=["Estado"])
def estado() -> dict:
    """Comprueba que PostgreSQL y el intermediario de mensajes responden."""
    base_de_datos = verificar_conexion()
    try:
        intermediario = bool(celery_app.connection().ensure_connection(max_retries=1))
    except Exception:
        intermediario = False
    return {
        "plataforma": configuracion.NOMBRE,
        "version": configuracion.VERSION,
        "entorno": configuracion.ENTORNO,
        "base_de_datos": "disponible" if base_de_datos else "sin conexión",
        "intermediario_de_mensajes": "disponible" if intermediario else "sin conexión",
        "estado": "operativo" if base_de_datos and intermediario else "degradado",
    }
