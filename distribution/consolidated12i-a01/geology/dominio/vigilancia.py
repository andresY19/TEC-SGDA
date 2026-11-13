"""
Edición simultánea, alertas y registro de descargas.

Edición simultánea. Cuando alguien abre una hoja de control o una ficha, queda registrado que la
tiene abierta y renueva ese registro con un latido cada 30 segundos. Si otra persona la abre
mientras la primera sigue ahí, la plataforma avisa a las dos, a la líder y a la administradora, y
anota quién la tenía abierta. Además, al guardar, si alguien guardó después de que esta persona
la abrió, el guardado se detiene y se le dice quién fue y a qué hora; puede recargar o guardar de
todos modos, y en ese caso la bitácora lo deja dicho. La plataforma nunca decide cuál versión
gana: avisa y deja la decisión a la persona.

Descargas. Se registran por una capa que mira toda respuesta con archivo adjunto, de modo que no
depende de que cada ruta se acuerde de anotar, y una descarga nueva queda registrada sin tocar nada.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

VENTANA_SEGUNDOS = 90          # sin latido en este tiempo, la persona se da por salida
SILENCIO_MINUTOS = 10          # no se repite la misma alerta en este lapso

LUGARES = {"hoja": "la hoja de control", "ficha": "la ficha de descripción"}


def _ahora(db: Session) -> datetime:
    """Hora del servidor de base de datos, la misma con la que se estampan las demás columnas."""
    return db.query(func.now()).scalar().replace(tzinfo=None)


def _alertar(db: Session, correo: str, tipo: str, titulo: str, mensaje: str, carpeta: str | None,
             ahora: datetime) -> bool:
    from geology.modelos import Alerta
    desde = ahora - timedelta(minutes=SILENCIO_MINUTOS)
    repetida = (db.query(Alerta).filter(Alerta.destinatario == correo, Alerta.tipo == tipo,
                                        Alerta.codigo_carpeta == carpeta, Alerta.mensaje == mensaje,
                                        Alerta.creada_en >= desde).first())
    if repetida:
        return False
    db.add(Alerta(destinatario=correo, tipo=tipo, titulo=titulo, mensaje=mensaje, codigo_carpeta=carpeta,
                  creada_en=ahora))
    return True


def direccion(db: Session) -> list:
    """Líder y administradora activas: quienes reciben todo aviso de edición simultánea."""
    from geology.modelos import UsuarioBD
    return db.query(UsuarioBD).filter(UsuarioBD.activo.is_(True),
                                      UsuarioBD.rol.in_(("administradora", "lider"))).all()


def abrir(db: Session, quien, codigo: str, lugar: str = "hoja") -> dict:
    """Registra o renueva que `quien` tiene abierta la carpeta; avisa si ya había alguien más."""
    from geology.modelos import Expediente, SesionEdicion
    lugar = lugar if lugar in LUGARES else "hoja"
    ahora = _ahora(db)
    viva = ahora - timedelta(seconds=VENTANA_SEGUNDOS)
    propia = (db.query(SesionEdicion).filter(SesionEdicion.codigo_carpeta == codigo, SesionEdicion.lugar == lugar,
                                             SesionEdicion.correo == quien.correo, SesionEdicion.cerrada.is_(False),
                                             SesionEdicion.ultimo_latido >= viva).first())
    nueva = propia is None
    if propia:
        propia.ultimo_latido = ahora
    else:
        db.add(SesionEdicion(codigo_carpeta=codigo, lugar=lugar, correo=quien.correo, nombre=quien.nombre,
                             abierta_en=ahora, ultimo_latido=ahora))
    db.flush()
    otros = (db.query(SesionEdicion).filter(SesionEdicion.codigo_carpeta == codigo, SesionEdicion.lugar == lugar,
                                            SesionEdicion.correo != quien.correo, SesionEdicion.cerrada.is_(False),
                                            SesionEdicion.ultimo_latido >= viva).all())
    if nueva and otros:
        donde = LUGARES[lugar]
        nombres = ", ".join(sorted({o.nombre for o in otros}))
        titulo = f"Dos personas tienen abierta {donde} de {codigo}"
        # A quien abre se le dice quién la tenía; a quienes ya la tenían se les dice quién llegó;
        # a la dirección se le dice todo.
        _alertar(db, quien.correo, "edicion_simultanea", titulo,
                 f"{nombres} ya tiene{'n' if len(otros) > 1 else ''} abierta {donde}. Si guarda sin avisarle, "
                 "uno de los dos puede pisar el trabajo del otro. Hablen antes de guardar.", codigo, ahora)
        for o in otros:
            _alertar(db, o.correo, "edicion_simultanea", titulo,
                     f"{quien.nombre} acaba de abrir {donde}, que usted tiene abierta. Si guarda sin avisarle, "
                     "uno de los dos puede pisar el trabajo del otro. Hablen antes de guardar.", codigo, ahora)
        involucrados = {quien.correo} | {o.correo for o in otros}
        for d in direccion(db):
            if d.correo not in involucrados:
                _alertar(db, d.correo, "edicion_simultanea", titulo,
                         f"{quien.nombre} y {nombres} tienen abierta {donde} al mismo tiempo.", codigo, ahora)
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == codigo).first()
    db.commit()
    return {"carpeta": codigo, "lugar": lugar,
            "otros": [{"nombre": o.nombre, "desde": o.abierta_en.isoformat(timespec="minutes")} for o in otros],
            "version": exp.actualizado_en.isoformat() if exp and exp.actualizado_en else None}


def cerrar(db: Session, quien, codigo: str, lugar: str | None = None) -> None:
    from geology.modelos import SesionEdicion
    q = db.query(SesionEdicion).filter(SesionEdicion.codigo_carpeta == codigo, SesionEdicion.correo == quien.correo,
                                       SesionEdicion.cerrada.is_(False))
    if lugar:
        q = q.filter(SesionEdicion.lugar == lugar)
    for s in q.all():
        s.cerrada = True
    db.commit()


def verificar_version(db: Session, exp, quien, version: str | None, forzar: bool, lugar: str = "hoja") -> str | None:
    """
    Devuelve el mensaje de conflicto, o None si se puede guardar. Hay conflicto cuando la carpeta
    cambió después de la versión que esta persona abrió y quien la cambió fue otra persona.
    """
    from geology.modelos import Trazabilidad
    if not version or not exp or not exp.actualizado_en:
        return None
    try:
        abierta = datetime.fromisoformat(version)
    except ValueError:
        return None
    if exp.actualizado_en <= abierta + timedelta(milliseconds=5):
        return None
    ultimo = (db.query(Trazabilidad).filter(Trazabilidad.expediente_id == exp.id)
              .order_by(Trazabilidad.fecha.desc(), Trazabilidad.id.desc()).first())
    otro = ultimo.usuario if ultimo and ultimo.usuario and ultimo.usuario != quien.nombre else None
    if not otro:
        return None
    hora = exp.actualizado_en.strftime("%H:%M")
    if forzar:
        return None
    return (f"{otro} guardó {LUGARES.get(lugar, 'esta carpeta')} a las {hora}, después de que usted la abrió. "
            "No se guardó nada. Recargue para ver sus cambios o confirme que quiere guardar de todos modos.")


def avisar_pisado(db: Session, quien, codigo: str, forzado: bool, lugar: str = "hoja") -> None:
    """Cuando alguien guarda de todos modos, se avisa a quien había guardado antes y a la dirección."""
    if not forzado:
        return
    from geology.modelos import Expediente, Trazabilidad
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == codigo).first()
    ultimo = (db.query(Trazabilidad).filter(Trazabilidad.expediente_id == exp.id)
              .order_by(Trazabilidad.fecha.desc(), Trazabilidad.id.desc()).first()) if exp else None
    ahora = _ahora(db)
    previo = ultimo.usuario if ultimo else None
    from geology.modelos import UsuarioBD
    destinos = {d.correo for d in direccion(db)}
    if previo:
        u = db.query(UsuarioBD).filter(UsuarioBD.nombre == previo).first()
        if u:
            destinos.add(u.correo)
    destinos.discard(quien.correo)
    for c in destinos:
        _alertar(db, c, "guardado_de_todos_modos", f"Se guardó encima de otro cambio en {codigo}",
                 f"{quien.nombre} guardó {LUGARES.get(lugar)} sabiendo que {previo or 'otra persona'} había guardado antes. "
                 "Revise que no se haya perdido nada.", codigo, ahora)


# ---------------------------------------------------------------- alertas
def mis_alertas(db: Session, correo: str, solo_nuevas: bool = True, limite: int = 50) -> list[dict]:
    from geology.modelos import Alerta
    q = db.query(Alerta).filter(Alerta.destinatario == correo)
    if solo_nuevas:
        q = q.filter(Alerta.leida_en.is_(None))
    return [{"id": a.id, "tipo": a.tipo, "titulo": a.titulo, "mensaje": a.mensaje, "carpeta": a.codigo_carpeta,
             "creada_en": a.creada_en.isoformat(timespec="seconds"), "leida": a.leida_en is not None}
            for a in q.order_by(Alerta.creada_en.desc()).limit(limite).all()]


def marcar_leidas(db: Session, correo: str, ids: list[int] | None = None) -> int:
    from geology.modelos import Alerta
    q = db.query(Alerta).filter(Alerta.destinatario == correo, Alerta.leida_en.is_(None))
    if ids:
        q = q.filter(Alerta.id.in_(ids))
    n = 0
    ahora = _ahora(db)
    for a in q.all():
        a.leida_en = ahora
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- descargas
_INSTRUMENTOS = [
    (r"^/instrumentos/fuid", "Inventario de salida FUID F-GDM-003"),
    (r"^/instrumentos/base-isadg-plantilla", "Base ISAD(G) en la plantilla del contrato"),
    (r"^/instrumentos/base-isadg", "Base de descripción ISAD(G)"),
    (r"^/instrumentos/hojas-de-control", "Hojas de control F-GDM-007"),
    (r"^/instrumentos/paquete-oficial", "Paquete oficial de instrumentos"),
    (r"^/entrega/paquete", "Paquete de entrega"),
    (r"^/consulta/", "Descarga de la entidad"),
    (r"^/unidades/[^/]+/hoja-de-control\.xlsx", "Hoja de control F-GDM-007 de una carpeta"),
    (r"^/unidades/[^/]+/testigo\.xlsx", "Testigo documental F-GDM-009"),
    (r"^/unidades/calidad", "Informe de calidad"),
    (r"^/cargue/calidad/", "Informe de calidad de una carpeta"),
    (r"^/ubicacion/.*rotulos", "Rótulos de caja y carpetas"),
    (r"^/ubicacion/propuesta/excel", "Propuesta de inventario de salida"),
    (r"^/seguimiento/excel", "Informe de seguimiento"),
    (r"^/contrato/pagos/\d+/f-fin-007", "F-FIN-007 informe del supervisor"),
    (r"^/contrato/documentos/.*/descargar", "Documento del contrato"),
    (r"^/contrato/eliminacion/", "Acta o inventario de eliminación"),
    (r"^/apoyo/", "Inventario de documentos de apoyo"),
    (r"^/vigilancia/descargas", "Registro de descargas"),
]


def nombre_del_instrumento(ruta: str) -> str:
    for patron, nombre in _INSTRUMENTOS:
        if re.search(patron, ruta):
            return nombre
    return "Otro archivo"


def registrar_descarga(db: Session, cuenta, ruta: str, consulta: str, archivo: str, tamano: int | None, ip: str,
                       inline: bool = False) -> None:
    from geology.modelos import DescargaRegistro
    db.add(DescargaRegistro(correo=cuenta.correo, nombre=cuenta.nombre, rol=cuenta.rol,
                            instrumento=("Imagen digitalizada consultada por la entidad" if inline else nombre_del_instrumento(ruta)), ruta=ruta[:300], filtros=(consulta or None),
                            archivo=(archivo or None), bytes=tamano, ip=(ip or None)))
    db.commit()


def listar_descargas(db: Session, desde=None, hasta=None, correo: str | None = None,
                     instrumento: str | None = None, limite: int = 500) -> dict:
    from geology.modelos import DescargaRegistro as D
    q = db.query(D)
    if desde:
        q = q.filter(D.fecha >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        q = q.filter(D.fecha < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
    if correo:
        q = q.filter(D.correo == correo)
    if instrumento:
        q = q.filter(D.instrumento == instrumento)
    total = q.count()
    filas = q.order_by(D.fecha.desc()).limit(limite).all()
    por_persona = {}
    por_instrumento = {}
    for f in q.all():
        por_persona[f.nombre] = por_persona.get(f.nombre, 0) + 1
        por_instrumento[f.instrumento] = por_instrumento.get(f.instrumento, 0) + 1
    return {"total": total,
            "por_persona": sorted(({"nombre": k, "descargas": v} for k, v in por_persona.items()), key=lambda x: -x["descargas"]),
            "por_instrumento": sorted(({"instrumento": k, "descargas": v} for k, v in por_instrumento.items()), key=lambda x: -x["descargas"]),
            "filas": [{"fecha": f.fecha.isoformat(timespec="seconds"), "nombre": f.nombre, "correo": f.correo, "rol": f.rol,
                       "instrumento": f.instrumento, "archivo": f.archivo, "filtros": f.filtros, "bytes": f.bytes, "ip": f.ip}
                      for f in filas]}
