"""
Ingreso, contraseñas y competencias.

Cada persona entra con su correo y su contraseña. El servidor entrega un pase firmado que
el navegador guarda y presenta en cada petición. La contraseña no se guarda en ninguna
parte: solo su huella.

La clave que se entrega al crear el usuario es provisional y el sistema obliga a cambiarla
en el primer ingreso, de modo que ninguna clave escrita en una hoja de cálculo siga
sirviendo después.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from geology.nucleo.bd import obtener_sesion
from geology.nucleo import sesiones
from geology.nucleo.pases import GEOLOGY_HORAS_SESION, crear_pase, leer_pase, llave_configurada
from geology.modelos import UsuarioBD, cifrar_clave, clave_correcta
from geology.dominio.estados import Funcion, Rol, Usuario

router = APIRouter(prefix="/cuentas", tags=["Usuarios"])

INTENTOS_MAXIMOS = 6
LARGO_MINIMO = 8


class Ingreso(BaseModel):
    correo: str
    clave: str


class CambioDeClave(BaseModel):
    clave_actual: str
    clave_nueva: str = Field(min_length=LARGO_MINIMO)


class CuentaNueva(BaseModel):
    nombre: str = Field(min_length=3, max_length=150)
    correo: str = Field(min_length=5, max_length=150)
    cargo: str = ""
    rol: str = "equipo"
    funcion: str = "Ambas"
    clave: str = ""          # vacía: la plataforma genera una provisional


class Habilitaciones(BaseModel):
    hojas_control: bool | None = None
    isadg: bool | None = None
    fuid: bool | None = None
    imagenes: bool | None = None


class CambioDeCuenta(BaseModel):
    nombre: str | None = None
    cargo: str | None = None
    rol: str | None = None
    funcion: str | None = None
    activo: bool | None = None


def _a_usuario(u: UsuarioBD) -> Usuario:
    """Convierte el registro de la base al objeto con el que razonan las reglas."""
    return Usuario(nombre=u.nombre, correo=u.correo, rol=Rol(u.rol), funcion=Funcion(u.funcion),
                   ve_hojas_control=bool(u.ve_hojas_control if u.ve_hojas_control is not None else True),
                   ve_isadg=bool(u.ve_isadg if u.ve_isadg is not None else True),
                   ve_fuid=bool(u.ve_fuid if u.ve_fuid is not None else True),
                   ve_imagenes=bool(u.ve_imagenes),
                   sin_limites=bool(getattr(u, "sin_limites", False)),
                   aprueba_lo_propio=bool(getattr(u, "aprueba_lo_propio", False)))


# Lo único que una cuenta de la entidad puede pedir. Todo lo demás —cargue, hojas en proceso,
# reparto de trabajo, centro de control— le responde 403 aunque conozca la dirección.
RUTAS_DE_LA_ENTIDAD = ("/consulta", "/cuentas/yo", "/cuentas/cambiar-clave", "/cuentas/salir", "/estado")


def usuario_actual(request: Request, authorization: str = Header(default=""),
                   db: Session = Depends(obtener_sesion)) -> Usuario:
    """Identifica a quien hace la petición por su pase firmado."""
    pase = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not pase:
        raise HTTPException(401, "Su sesión no está iniciada. Ingrese con su correo y contraseña.")
    correo = leer_pase(pase)
    if not correo:
        raise HTTPException(401, "Su sesión venció o el pase no es válido. Vuelva a ingresar.")
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo, UsuarioBD.activo.is_(True)).first()
    if not u:
        raise HTTPException(401, "Su sesión venció o el pase no es válido. Vuelva a ingresar.")
    try:
        vigente = sesiones.validar(pase, u.clave_hash)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "El registro de sesiones no está disponible.") from None
    if not vigente:
        raise HTTPException(401, "Su sesión venció o fue revocada. Vuelva a ingresar.")
    # Excepciones exactas por método y ruta; ningún prefijo habilita otras APIs.
    if u.debe_cambiar_clave and (request.method, request.url.path) not in {
        ("GET", "/cuentas/yo"), ("POST", "/cuentas/cambiar-clave"), ("POST", "/cuentas/salir"),
    }:
        raise HTTPException(403, "Debe cambiar su contraseña provisional antes de continuar.")
    if u.rol == Rol.ENTIDAD.value and not request.url.path.startswith(RUTAS_DE_LA_ENTIDAD):
        raise HTTPException(403, "Su cuenta es de consulta de la entidad y solo accede a la "
                                 "pestaña Consulta.")
    return _a_usuario(u)


def _ficha(u: UsuarioBD) -> dict:
    p = _a_usuario(u)
    return {
        "nombre": u.nombre, "correo": u.correo, "cargo": u.cargo,
        "lectura_ia_disponible": any(bool(__import__("os").environ.get(k, "").strip()) for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", *[f"GEMINI_API_KEY_{i}" for i in range(1, 8)]]),
        "rol": u.rol, "funcion": u.funcion, "activo": u.activo,
        "sin_limites": bool(getattr(u, "sin_limites", False)),
        "aprueba_lo_propio": bool(getattr(u, "aprueba_lo_propio", False)),
        "debe_cambiar_clave": u.debe_cambiar_clave,
        "ultimo_ingreso": u.ultimo_ingreso.isoformat(timespec="minutes") if u.ultimo_ingreso else None,
        "aprueba_descripcion": p.aprueba_descripcion,
        "revisa_hoja_control": p.revisa_hoja_control,
        "valida_descripcion": p.valida_descripcion,
        "elabora_descripcion": p.elabora_descripcion,
        "edita_hoja_control": p.edita_hoja_control,
        "puede_retirar": p.puede_retirar,
        "puede_devolver": p.puede_devolver,
        "pestanas": list(p.pestanas_visibles),
        "es_entidad": p.es_entidad,
        "habilitaciones": {"hojas_control": p.ve_hojas_control, "isadg": p.ve_isadg,
                           "fuid": p.ve_fuid, "imagenes": p.ve_imagenes},
    }


def _invalidar_sesiones(correo):
    try:
        sesiones.invalidar_usuario(correo)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "El registro de sesiones no está disponible; no se confirmó el cambio.") from None


@router.post("/salir", summary="Revocar la sesión actual")
def salir(request: Request, quien: Usuario = Depends(usuario_actual)) -> dict:
    pase = request.headers.get("authorization", "")[7:].strip()
    try:
        sesiones.revocar(pase)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "No se confirmó el cierre de sesión. Intente de nuevo.") from None
    return {"mensaje": "Sesión revocada."}


@router.post("/ingresar", summary="Ingresar con correo y contraseña")
def ingresar(datos: Ingreso, db: Session = Depends(obtener_sesion)) -> dict:
    if not llave_configurada():
        raise HTTPException(503, "El servicio de sesiones no está configurado.")
    correo = datos.correo.strip().lower()
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo).populate_existing().with_for_update().first()

    # El mismo mensaje para correo inexistente y clave errada, para no revelar quién existe.
    generico = "El correo o la contraseña no coinciden."
    if not u or not u.activo:
        raise HTTPException(401, generico)
    if u.intentos_fallidos >= INTENTOS_MAXIMOS:
        raise HTTPException(423, "Su usuario quedó bloqueado por intentos fallidos. "
                                 "Pida a la dirección del proyecto que lo desbloquee.")
    if not clave_correcta(datos.clave, u.clave_hash):
        u.intentos_fallidos += 1
        db.commit()
        restantes = INTENTOS_MAXIMOS - u.intentos_fallidos
        raise HTTPException(401, generico + (f" Le quedan {restantes} intentos."
                                             if restantes <= 3 else ""))

    u.intentos_fallidos = 0
    u.ultimo_ingreso = datetime.now()
    pase = crear_pase(u.correo)
    try:
        sesiones.registrar(pase, u.clave_hash)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "El registro de sesiones no está disponible.") from None
    db.commit()
    return {"pase": pase, "horas": GEOLOGY_HORAS_SESION,
            "usuario": _ficha(u),
            "aviso_llave": None}


@router.post("/cambiar-clave", summary="Cambiar la propia contraseña")
def cambiar_clave(datos: CambioDeClave, db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)) -> dict:
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == quien.correo).populate_existing().with_for_update().first()
    if not clave_correcta(datos.clave_actual, u.clave_hash):
        raise HTTPException(401, "La contraseña actual no coincide.")
    if datos.clave_nueva == datos.clave_actual:
        raise HTTPException(422, "La contraseña nueva debe ser distinta de la actual.")
    if len(datos.clave_nueva) < LARGO_MINIMO:
        raise HTTPException(422, f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres.")
    _invalidar_sesiones(u.correo)
    u.clave_hash = cifrar_clave(datos.clave_nueva)
    u.debe_cambiar_clave = False
    db.commit()
    nuevo_pase = crear_pase(u.correo)
    try:
        sesiones.registrar(nuevo_pase, u.clave_hash)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "Contraseña actualizada; vuelva a ingresar cuando el registro de sesiones esté disponible.") from None
    return {"mensaje": "Contraseña cambiada. Las sesiones anteriores fueron revocadas.", "pase": nuevo_pase, "horas": GEOLOGY_HORAS_SESION}


@router.get("/yo", summary="Quién soy y qué puedo hacer")
def yo(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    return _ficha(db.query(UsuarioBD).filter(UsuarioBD.correo == quien.correo).first())


@router.get("", summary="Equipo del contrato")
def listar(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    if quien.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Solo la dirección del proyecto ve el equipo completo.")
    return [_ficha(u) for u in db.query(UsuarioBD).order_by(UsuarioBD.nombre).all()]


@router.post("/{correo}/restablecer", summary="Restablecer la contraseña de alguien del equipo")
def restablecer(correo: str, db: Session = Depends(obtener_sesion),
                quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Genera una clave provisional que la persona deberá cambiar al entrar. Sirve para el olvido
    y para desbloquear a quien falló demasiadas veces.
    """
    if quien.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Restablecer contraseñas lo hace la dirección del proyecto.")
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo.strip().lower()).populate_existing().with_for_update().first()
    if not u:
        raise HTTPException(404, f"{correo} no está registrado.")
    import secrets
    provisional = "Geology-" + secrets.token_urlsafe(6)
    _invalidar_sesiones(u.correo)
    u.clave_hash = cifrar_clave(provisional)
    u.debe_cambiar_clave = True
    u.intentos_fallidos = 0
    db.commit()
    return {"correo": u.correo, "clave_provisional": provisional,
            "mensaje": "Entréguesela en persona. La plataforma le exigirá cambiarla al entrar."}


def _solo_direccion(quien: Usuario) -> None:
    if quien.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Administrar cuentas lo hace la dirección del proyecto.")


def _validar_rol_y_funcion(rol: str, funcion: str) -> tuple[str, str]:
    try:
        Rol(rol)
    except ValueError:
        raise HTTPException(422, f"Rol «{rol}» no existe. Use: "
                                 + ", ".join(r.value for r in Rol))
    try:
        Funcion(funcion)
    except ValueError:
        raise HTTPException(422, f"Función «{funcion}» no existe. Use: "
                                 + ", ".join(f.value for f in Funcion))
    return rol, funcion


@router.post("/crear", summary="Crear una cuenta (equipo o entidad)")
def crear(datos: CuentaNueva, db: Session = Depends(obtener_sesion),
          quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Crea a una persona del equipo o una cuenta de consulta para la entidad contratante.

    Si no se escribe clave, se genera una provisional. En cualquier caso la plataforma exige
    cambiarla en el primer ingreso.
    """
    _solo_direccion(quien)
    correo = datos.correo.strip().lower()
    if "@" not in correo:
        raise HTTPException(422, "El correo no tiene forma de correo.")
    if db.query(UsuarioBD).filter(UsuarioBD.correo == correo).first():
        raise HTTPException(409, f"{correo} ya está registrado.")
    rol, funcion = _validar_rol_y_funcion(datos.rol, datos.funcion)
    import secrets
    provisional = datos.clave.strip() or ("Geology-" + secrets.token_urlsafe(6))
    if len(provisional) < LARGO_MINIMO:
        raise HTTPException(422, f"La clave debe tener al menos {LARGO_MINIMO} caracteres.")
    u = UsuarioBD(nombre=datos.nombre.strip(), cargo=datos.cargo.strip() or None, correo=correo,
                  rol=rol, funcion=funcion, clave_hash=cifrar_clave(provisional),
                  debe_cambiar_clave=True, activo=True,
                  ve_hojas_control=True, ve_isadg=True, ve_fuid=True,
                  ve_imagenes=False)
    db.add(u)
    db.commit()
    return {"cuenta": _ficha(u), "clave_provisional": provisional,
            "mensaje": "Cuenta creada. Entregue la clave provisional en persona; la plataforma "
                       "exigirá cambiarla al entrar."}


@router.put("/{correo}", summary="Cambiar datos, rol o estado de una cuenta")
def cambiar(correo: str, datos: CambioDeCuenta, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    _solo_direccion(quien)
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo.strip().lower()).populate_existing().with_for_update().first()
    if not u:
        raise HTTPException(404, f"{correo} no está registrado.")
    if datos.rol is not None or datos.funcion is not None:
        _validar_rol_y_funcion(datos.rol or u.rol, datos.funcion or u.funcion)
    if u.correo == quien.correo and datos.activo is False:
        raise HTTPException(409, "No puede desactivar su propia cuenta.")
    if u.correo == quien.correo and datos.rol not in (None, Rol.ADMINISTRADORA.value):
        raise HTTPException(409, "No puede quitarse a sí misma el rol de administradora.")
    if datos.activo is False:
        _invalidar_sesiones(u.correo)
    for campo in ("nombre", "cargo", "rol", "funcion", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(u, campo, valor.strip() if isinstance(valor, str) else valor)
    if datos.activo:
        u.intentos_fallidos = 0
    db.commit()
    return _ficha(u)


@router.put("/{correo}/habilitaciones", summary="Qué puede ver una cuenta de la entidad")
def habilitar(correo: str, datos: Habilitaciones, db: Session = Depends(obtener_sesion),
              quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Prende o apaga, para una cuenta de la entidad, cada cosa que puede consultar: hojas de
    control, base ISAD(G), inventario FUID e imágenes digitalizadas. Lo que no se manda no
    cambia.
    """
    _solo_direccion(quien)
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo.strip().lower()).populate_existing().with_for_update().first()
    if not u:
        raise HTTPException(404, f"{correo} no está registrado.")
    if u.rol != Rol.ENTIDAD.value:
        raise HTTPException(409, "Las habilitaciones de consulta solo aplican a cuentas de la "
                                 "entidad (rol «entidad»).")
    mapa = {"hojas_control": "ve_hojas_control", "isadg": "ve_isadg",
            "fuid": "ve_fuid", "imagenes": "ve_imagenes"}
    for clave, columna in mapa.items():
        valor = getattr(datos, clave)
        if valor is not None:
            setattr(u, columna, bool(valor))
    db.commit()
    return _ficha(u)


class SinLimites(BaseModel):
    activo: bool


@router.put("/{correo}/sin-limites", summary="Casilla «sin límites» para cubrir una ausencia")
def sin_limites(correo: str, datos: SinLimites, db: Session = Depends(obtener_sesion),
                quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    La administradora le da a una persona del equipo todos los permisos de trabajo del flujo
    (hoja de control, descripción, validar, aprobar, devolver, retirar) mientras cubre a
    alguien que no vino, y se los quita cuando termina. Todo lo que haga queda en la bitácora
    con su nombre. No aplica a la administradora (ya los tiene) ni a perfiles de consulta o de
    la entidad.
    """
    _solo_direccion(quien)
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo.strip().lower()).populate_existing().with_for_update().first()
    if not u:
        raise HTTPException(404, f"{correo} no está registrado.")
    if u.rol in (Rol.ADMINISTRADORA.value, Rol.CONSULTA.value, Rol.ENTIDAD.value):
        raise HTTPException(409, "La casilla «sin límites» solo aplica a personas del equipo "
                                 "(rol «equipo» o «líder»).")
    u.sin_limites = bool(datos.activo)
    db.commit()
    return _ficha(u)


@router.put("/{correo}/aprueba-lo-propio", summary="Permitir que una persona apruebe lo que ella misma elaboró")
def aprueba_lo_propio(correo: str, datos: SinLimites, db: Session = Depends(obtener_sesion),
                      quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    La administradora decide quién puede aprobar incluso su propio trabajo. La carpeta sigue
    pasando por todos los estados (hoja revisada, descripción por validar, validada, aprobada):
    esta casilla solo quita el bloqueo de que quien elaboró no apruebe, y la bitácora deja
    escrito que la aprobación fue propia. También le da a la persona la facultad de aprobar.
    No aplica a la administradora ni a los perfiles de consulta o de la entidad.
    """
    _solo_direccion(quien)
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo.strip().lower()).populate_existing().with_for_update().first()
    if not u:
        raise HTTPException(404, f"{correo} no está registrado.")
    if u.rol in (Rol.ADMINISTRADORA.value, Rol.CONSULTA.value, Rol.ENTIDAD.value):
        raise HTTPException(409, "Esta casilla solo aplica a personas del equipo (rol «equipo» o «líder»).")
    u.aprueba_lo_propio = bool(datos.activo)
    db.commit()
    return _ficha(u)

