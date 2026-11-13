"""Sesiones locales nuevas, incompatibles con tokens originales no documentados.

Formato g1.base64url(JSON).base64url(HMAC-SHA256), autenticado, no cifrado.
Solo usa primitivas de la biblioteca estándar; no carga .env ni consulta servicios.
La clave debe generarse aleatoriamente, independiente de otras instalaciones.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time


def _horas():
    try:
        horas = int(os.environ.get("GEOLOGY_HORAS_SESION", "8"))
        if not 1 <= horas <= 24:
            raise ValueError
        return horas
    except (ValueError, TypeError):
        raise RuntimeError("GEOLOGY_HORAS_SESION debe ser un entero entre 1 y 24.") from None


GEOLOGY_HORAS_SESION = _horas()
_PROPOSITO = b"geology-local-session:g1:"


def _llave():
    clave = os.environ.get("GEOLOGY_CLAVE", "")
    try:
        datos = clave.encode("utf-8")
    except UnicodeError:
        raise RuntimeError("GEOLOGY_CLAVE tiene un formato inválido.") from None
    if len(datos) < 32 or clave != clave.strip():
        raise RuntimeError("GEOLOGY_CLAVE requiere una clave local independiente de al menos 32 bytes.")
    return datos


def llave_configurada() -> bool:
    try:
        _llave()
        return True
    except (RuntimeError, UnicodeError):
        return False


def _b64(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _decodificar(texto):
    if not texto or not re.fullmatch(r"[A-Za-z0-9_-]+", texto):
        raise ValueError
    datos = base64.b64decode(texto + "=" * (-len(texto) % 4), altchars=b"-_", validate=True)
    if _b64(datos) != texto:
        raise ValueError
    return datos


def _correo(valor):
    if not isinstance(valor, str) or not 3 <= len(valor) <= 150:
        raise ValueError("Identidad de sesión inválida.")
    if valor != valor.strip().lower() or valor.count("@") != 1 or any(c.isspace() or ord(c) < 32 for c in valor):
        raise ValueError("Identidad de sesión inválida.")
    if not all(valor.split("@")):
        raise ValueError("Identidad de sesión inválida.")
    return valor


def crear_pase(correo: str) -> str:
    clave = _llave()  # Sin clave de respaldo ni generación implícita.
    correo = _correo(correo.strip().lower() if isinstance(correo, str) else correo)
    ahora = int(time.time())
    contenido = {"sub": correo, "iat": ahora, "exp": ahora + GEOLOGY_HORAS_SESION * 3600,
                 "jti": secrets.token_urlsafe(16)}
    cuerpo = _b64(json.dumps(contenido, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii"))
    mensaje = ("g1." + cuerpo).encode("ascii")
    firma = hmac.digest(clave, _PROPOSITO + mensaje, hashlib.sha256)
    return mensaje.decode("ascii") + "." + _b64(firma)


def detalles_pase(pase: str) -> dict | None:
    """Devuelve correo autenticado o None; no registra tokens ni errores internos."""
    try:
        if not isinstance(pase, str) or len(pase) > 2048:
            return None
        version, cuerpo, firma = pase.split(".")
        if version != "g1":
            return None
        recibida = _decodificar(firma)
        esperada = hmac.digest(_llave(), _PROPOSITO + (version + "." + cuerpo).encode("ascii"), hashlib.sha256)
        if len(recibida) != 32 or not hmac.compare_digest(recibida, esperada):
            return None
        raw = _decodificar(cuerpo)
        datos = json.loads(raw)
        if not isinstance(datos, dict) or set(datos) != {"sub", "iat", "exp", "jti"}:
            return None
        # Canonicalización rechaza claves repetidas y representaciones ambiguas.
        if json.dumps(datos, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii") != raw:
            return None
        if type(datos["iat"]) is not int or type(datos["exp"]) is not int:
            return None
        ahora = int(time.time())
        if not 0 <= datos["iat"] <= ahora < datos["exp"]:
            return None
        if not 0 < datos["exp"] - datos["iat"] <= GEOLOGY_HORAS_SESION * 3600:
            return None
        if not isinstance(datos["jti"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{22}", datos["jti"]):
            return None
        _correo(datos["sub"])
        return datos
    except (ValueError, TypeError, UnicodeError, RuntimeError, RecursionError):
        return None


def leer_pase(pase: str) -> str | None:
    """Sólo firma y expiración. Autorizar requiere además sesiones.validar()."""
    claims = detalles_pase(pase)
    return claims["sub"] if claims else None
