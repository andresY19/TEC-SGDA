"""Aplica la propuesta exclusivamente a la copia C: registrada en el preflight."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
CTX=Path(json.loads((ROOT/'phase11b-preflight.json').read_text())['context'])
assert CTX.resolve()!=ROOT.resolve() and CTX.drive.lower()=='c:'


def read(name):return (ROOT/name).read_text(encoding='utf-8')
def write(name,text):(CTX/name).write_text(text,encoding='utf-8')


s=read('geology/nucleo/pases.py')
s=s.replace('def leer_pase(pase: str) -> str | None:', 'def detalles_pase(pase: str) -> dict | None:')
s=s.replace('        return _correo(datos["sub"])','        _correo(datos["sub"])\n        return datos')
s+='''\n\ndef leer_pase(pase: str) -> str | None:
    """Sólo firma y expiración. Autorizar requiere además sesiones.validar()."""
    claims = detalles_pase(pase)
    return claims["sub"] if claims else None
'''
write('geology/nucleo/pases.py',s)
s=read('geology/rutas/cuentas.py')
s=s.replace('from geology.nucleo.bd import obtener_sesion','from geology.nucleo.bd import obtener_sesion\nfrom geology.nucleo import sesiones')
old='    if not u:\n        raise HTTPException(403, "Su usuario ya no está activo en GEOLOGY.")'
assert old in s
s=s.replace(old,'''    if not u:
        raise HTTPException(401, "Su sesión venció o el pase no es válido. Vuelva a ingresar.")
    try:
        vigente = sesiones.validar(pase, u.clave_hash)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "El registro de sesiones no está disponible.") from None
    if not vigente:
        raise HTTPException(401, "Su sesión venció o fue revocada. Vuelva a ingresar.")''')
s=s.replace('("POST", "/cuentas/cambiar-clave"),','("POST", "/cuentas/cambiar-clave"), ("POST", "/cuentas/salir"),')
s=s.replace('"/cuentas/cambiar-clave", "/estado")','"/cuentas/cambiar-clave", "/cuentas/salir", "/estado")')
s=s.replace('filter(UsuarioBD.correo == correo).first()','filter(UsuarioBD.correo == correo).populate_existing().with_for_update().first()',1)
s=s.replace('    db.commit()\n    return {"pase": crear_pase(u.correo)', '''    pase = crear_pase(u.correo)
    try:
        sesiones.registrar(pase, u.clave_hash)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "El registro de sesiones no está disponible.") from None
    db.commit()
    return {"pase": pase''',1)
s=s.replace('filter(UsuarioBD.correo == quien.correo).first()\n    if not clave_correcta','filter(UsuarioBD.correo == quien.correo).populate_existing().with_for_update().first()\n    if not clave_correcta',1)
s=s.replace('    u.clave_hash = cifrar_clave(datos.clave_nueva)','    _invalidar_sesiones(u.correo)\n    u.clave_hash = cifrar_clave(datos.clave_nueva)',1)
old='    return {"mensaje": "Contraseña cambiada. Su clave anterior ya no sirve."}'
assert old in s
s=s.replace(old,'''    nuevo_pase = crear_pase(u.correo)
    try:
        sesiones.registrar(nuevo_pase, u.clave_hash)
    except sesiones.SesionesNoDisponibles:
        raise HTTPException(503, "Contraseña actualizada; vuelva a ingresar cuando el registro de sesiones esté disponible.") from None
    return {"mensaje": "Contraseña cambiada. Las sesiones anteriores fueron revocadas.", "pase": nuevo_pase, "horas": GEOLOGY_HORAS_SESION}''')
s=s.replace('filter(UsuarioBD.correo == correo.strip().lower()).first()','filter(UsuarioBD.correo == correo.strip().lower()).populate_existing().with_for_update().first()')
s=s.replace('    u.clave_hash = cifrar_clave(provisional)','    _invalidar_sesiones(u.correo)\n    u.clave_hash = cifrar_clave(provisional)',1)
s=s.replace('    for campo in ("nombre", "cargo", "rol", "funcion", "activo"):', '    if datos.activo is False:\n        _invalidar_sesiones(u.correo)\n    for campo in ("nombre", "cargo", "rol", "funcion", "activo"):')
pos=s.index('\n\n@router.post("/ingresar"')
s=s[:pos]+'''\n\ndef _invalidar_sesiones(correo):
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
''' +s[pos:]
write('geology/rutas/cuentas.py',s)
s=read('geology/main.py').replace('        if not u:\n            return\n        archivo = ""', '''        if not u or not u.activo:
            return
        from geology.nucleo.sesiones import validar
        if not validar(pase, u.clave_hash):
            return
        archivo = ""''',1)
write('geology/main.py',s)
s=read('geology/interfaz/index.html')
s=s.replace('    await pedir("/cuentas/cambiar-clave",','    const cambio = await pedir("/cuentas/cambiar-clave",',1)
s=s.replace('    SESION = await pedir("/cuentas/yo");','    PASE = cambio.pase;\n    SESION = await pedir("/cuentas/yo");',1)
pos=s.index('async function entrar(){')
s=s[:pos]+'''async function salirDeLaSesion(){
  try {
    await pedir("/cuentas/salir", {method:"POST"});
    latir(false); PASE = null; SESION = null;
    window.location.reload();
  } catch (e) { alert("No se confirmó el cierre de sesión: " + e.message); }
}

'''+s[pos:]
pos=s.index('<span id="quienNombre"') if '<span id="quienNombre"' in s else s.index('<b id="quienNombre"')
s=s[:pos]+'<button class="btn2" onclick="salirDeLaSesion()">Cerrar sesión</button>'+s[pos:]
write('geology/interfaz/index.html',s)
print('Staged files only:',str(CTX))
