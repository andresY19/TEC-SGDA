"""
Consulta para la entidad contratante (Servicio Geológico Colombiano).

Es la ventana por la que la entidad revisa lo que el contrato va entregando sin que haya que
mandarle las hojas de control una por una: busca la carpeta, descarga su hoja de control en
el formato oficial F-GDM-007, descarga la base ISAD(G) y el inventario F-GDM-003 (FUID) de
lo que ya está en caja definitiva y, cuando la dirección del proyecto se lo habilita, mira
las imágenes digitalizadas.

Lo que se ve aquí es el resultado del trabajo archivístico y nada más: no hay bitácora de
proceso, ni reparto de trabajo, ni herramientas internas del equipo. Cada cosa se habilita o
deshabilita por cuenta desde la pestaña Cuentas.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from geology.nucleo.bd import obtener_sesion
from geology.modelos import Archivo, Caja, Expediente, Periodo
from geology.rutas import instrumentos
from geology.rutas.cuentas import usuario_actual
from geology.dominio import formatos_sgc as fmt
from geology.dominio.codigos import normalizar_codigo_carpeta
from geology.dominio.estados import Estado, Rol, Usuario
from geology.dominio.publicacion import es_publicable, nombre_publico
from geology.dominio.neutralidad import (con_descriptores, declaracion_pdfa, limpiar_respuesta,
                                         pdf_sin_metadatos, unir_pdfs)

router = APIRouter(prefix="/consulta", tags=["Consulta de la entidad"])

EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Desde qué estado se muestra cada instrumento. Una hoja de control se publica cuando ya fue
# revisada por el equipo; una descripción, cuando fue validada; el inventario, cuando la
# unidad ya está en su caja definitiva.
CON_HOJA = (Estado.HOJA_REVISADA.value, Estado.DESCRIPCION_POR_VALIDAR.value,
            Estado.DESCRIPCION_VALIDADA.value, Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value)
CON_DESCRIPCION = (Estado.DESCRIPCION_VALIDADA.value, Estado.ARCHIVADO.value,
                   Estado.EN_INVENTARIO.value)
EN_INVENTARIO = (Estado.EN_INVENTARIO.value,)

# Cómo se le nombra a la entidad cada etapa. Es vocabulario archivístico, no de proceso.
ETAPA = {
    Estado.HOJA_REVISADA.value: "Hoja de control revisada",
    Estado.DESCRIPCION_POR_VALIDAR.value: "Hoja de control revisada",
    Estado.DESCRIPCION_VALIDADA.value: "Descripción ISAD(G) validada",
    Estado.ARCHIVADO.value: "Descripción validada, pendiente de caja",
    Estado.EN_INVENTARIO.value: "En inventario de salida",
}


def _con_acceso(quien: Usuario) -> Usuario:
    """La pestaña es de la entidad; la dirección del proyecto entra para ver lo que ella ve."""
    if quien.rol not in (Rol.ENTIDAD, Rol.ADMINISTRADORA):
        raise HTTPException(403, "Esta consulta es para la entidad contratante.")
    return quien


def _habilitado(quien: Usuario, que: str) -> None:
    """La dirección siempre puede; a la entidad se le comprueba la habilitación."""
    if quien.rol is Rol.ADMINISTRADORA:
        return
    if not getattr(quien, que):
        raise HTTPException(403, "Este contenido no está habilitado para su cuenta. "
                                 "Solicítelo a la dirección del proyecto.")


def _ficha(db: Session, exp: Expediente) -> dict:
    c = instrumentos._contexto(db, exp)
    partes = db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta).count()
    return {
        "carpeta": exp.codigo_carpeta,
        "nombre": nombre_publico(exp),
        "periodo": c["periodo"].numero_romano if c["periodo"] else "",
        "serie": c["serie"].nombre if c["serie"] else "",
        "subserie": c["sub"].nombre if c["sub"] else "",
        "fecha_inicial": exp.fecha_inicial.isoformat() if exp.fecha_inicial else (exp.fechas_texto or ""),
        "fecha_final": exp.fecha_final.isoformat() if exp.fecha_final else "",
        "folios": exp.volumen_folios,
        "caja_origen": exp.caja_origen,
        "caja_definitiva": exp.caja_definitiva,
        "carpeta_en_caja": exp.consecutivo_en_caja,
        "codigo_referencia": exp.codigo_referencia,
        "etapa": ETAPA.get(exp.estado, ""),
        "tiene_hoja": exp.estado in CON_HOJA,
        "tiene_descripcion": exp.estado in CON_DESCRIPCION,
        "en_inventario": exp.estado in EN_INVENTARIO,
        "partes_digitalizadas": partes,
    }


@router.get("/yo", summary="Qué tiene habilitado esta cuenta")
def yo(quien: Usuario = Depends(usuario_actual)) -> dict:
    _con_acceso(quien)
    direccion = quien.rol is Rol.ADMINISTRADORA
    return {"hojas_control": direccion or quien.ve_hojas_control,
            "isadg": direccion or quien.ve_isadg,
            "fuid": direccion or quien.ve_fuid,
            "imagenes": direccion or quien.ve_imagenes}


@router.get("/resumen", summary="Cuánto hay publicado para consulta")
def resumen(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _con_acceso(quien)
    def cuantos(estados):
        filas = db.query(Expediente).filter(Expediente.estado.in_(estados)).all()
        return sum(1 for e in filas if es_publicable(db, e))
    cajas = (db.query(Caja).order_by(Caja.codigo).all())
    periodos = [p for (p,) in db.query(Periodo.numero_romano).order_by(Periodo.numero_romano).all()]
    return {
        "con_hoja_de_control": cuantos(CON_HOJA),
        "con_descripcion": cuantos(CON_DESCRIPCION),
        "en_inventario": cuantos(EN_INVENTARIO),
        "cajas": [{"codigo": c.codigo, "periodo": c.periodo, "carpetas": c.total_carpetas,
                   "cerrada": c.cerrada} for c in cajas],
        "periodos": periodos,
    }


@router.get("/unidades", summary="Buscar unidades documentales publicadas")
def unidades(buscar: str = Query("", description="Código de carpeta, nombre o código de referencia"),
             caja: str | None = None, periodo: str | None = None,
             limite: int = Query(300, le=2000),
             db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _con_acceso(quien)
    q = db.query(Expediente).filter(Expediente.estado.in_(CON_HOJA))
    texto = (buscar or "").strip()
    if texto:
        carpeta = normalizar_codigo_carpeta(texto)
        patron = f"%{texto}%"
        condiciones = [Expediente.titulo.ilike(patron), Expediente.codigo_referencia.ilike(patron),
                       Expediente.codigo_carpeta.ilike(patron)]
        if carpeta:
            condiciones.append(Expediente.codigo_carpeta == carpeta)
        q = q.filter(or_(*condiciones))
    if caja:
        q = q.filter(Expediente.caja_definitiva == caja.upper())
    if periodo:
        q = q.join(Periodo).filter(Periodo.numero_romano == periodo.upper())
    filas = (q.order_by(Expediente.caja_definitiva, Expediente.consecutivo_en_caja,
                        Expediente.codigo_carpeta).limit(limite).all())
    return [_ficha(db, e) for e in filas if es_publicable(db, e)]


@router.get("/unidades/{codigo_carpeta}", summary="Una unidad documental")
def unidad(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
           quien: Usuario = Depends(usuario_actual)) -> dict:
    _con_acceso(quien)
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
    if not exp or exp.estado not in CON_HOJA or not es_publicable(db, exp):
        raise HTTPException(404, f"{carpeta} no está publicada para consulta.")
    ficha = _ficha(db, exp)
    if quien.rol is Rol.ADMINISTRADORA or quien.ve_imagenes:
        ficha["partes"] = [{"parte": a.fragmento, "paginas": a.paginas,
                            "pagina_inicial": a.pagina_inicial, "pagina_final": a.pagina_final,
                            "disponible": Path(a.ruta).exists()}
                           for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
                                      .order_by(Archivo.fragmento).all()]
    return ficha


@router.get("/hoja-de-control/{codigo_carpeta}", summary="Hoja de control F-GDM-007 de una carpeta")
def hoja_de_control(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                    quien: Usuario = Depends(usuario_actual)):
    _con_acceso(quien)
    _habilitado(quien, "ve_hojas_control")
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
    if not exp or exp.estado not in CON_HOJA or not es_publicable(db, exp):
        raise HTTPException(404, f"{carpeta} no tiene hoja de control publicada.")
    contenido = fmt.hoja_de_control(instrumentos.datos_hoja_de_control(db, exp))
    return limpiar_respuesta(Response(contenido, media_type=EXCEL, headers={
        "Content-Disposition": f'attachment; filename="F-GDM-007_{carpeta}.xlsx"'}))


@router.get("/hojas-de-control", summary="Hojas de control F-GDM-007 por caja o periodo")
def hojas_de_control(caja: str | None = None, periodo: str | None = None,
                     limite: int = Query(300, le=1000),
                     db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    _con_acceso(quien)
    _habilitado(quien, "ve_hojas_control")
    expedientes = instrumentos._expedientes(db, list(CON_HOJA), caja, periodo,
                                            solo_publicables=True)[:limite]
    if not expedientes:
        raise HTTPException(404, "No hay hojas de control publicadas con ese filtro.")
    hojas = {f"F-GDM-007_{e.codigo_carpeta}.xlsx":
             fmt.hoja_de_control(instrumentos.datos_hoja_de_control(db, e)) for e in expedientes}
    if len(hojas) == 1:
        nombre, contenido = next(iter(hojas.items()))
        return limpiar_respuesta(Response(contenido, media_type=EXCEL,
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'}))
    nombre = ("HOJAS_DE_CONTROL" + (f"_{caja.upper()}" if caja else "")
              + (f"_periodo_{periodo.upper()}" if periodo else "") + f"_{date.today().isoformat()}.zip")
    return limpiar_respuesta(Response(fmt.paquete(hojas), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'}))


@router.get("/fuid", summary="Inventario F-GDM-003 (FUID) de lo que está en caja definitiva")
def fuid(caja: str | None = None, periodo: str | None = None,
         db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    _con_acceso(quien)
    _habilitado(quien, "ve_fuid")
    # Es exactamente el mismo inventario que expide el equipo: misma plantilla, mismos datos.
    return limpiar_respuesta(instrumentos.fuid(caja=caja, periodo=periodo, solo_inventariadas=True,
                                               solo_publicables=True, db=db, quien=quien))


@router.get("/isadg", summary="Base de descripción ISAD(G) en la plantilla del proyecto")
def isadg(solo_conservacion_total: bool = False,
          db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    _con_acceso(quien)
    _habilitado(quien, "ve_isadg")
    # Solo descripciones validadas: a la entidad nunca le llega un borrador.
    return limpiar_respuesta(instrumentos.base_isadg_en_plantilla(
        solo_conservacion_total=solo_conservacion_total, incluir_por_validar=False,
        solo_publicables=True, db=db, quien=quien))


@router.get("/previa/{cual}", summary="Ver en pantalla el FUID o la base ISAD(G) publicados")
def previa(cual: str, periodo: str | None = None, caja: str | None = None,
           buscar: str = Query(""), limite: int = Query(400, le=2000),
           db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    """Lo mismo que se descargaría, pero en pantalla. Solo lo publicado y sin errores."""
    _con_acceso(quien)
    if cual not in ("fuid", "isadg"):
        raise HTTPException(404, "Se puede ver «fuid» o «isadg».")
    _habilitado(quien, "ve_fuid" if cual == "fuid" else "ve_isadg")
    if cual == "fuid":
        r = instrumentos.fuid(caja=caja, periodo=periodo, solo_inventariadas=True,
                              solo_publicables=True, db=db, quien=quien)
    else:
        r = instrumentos.base_isadg_en_plantilla(solo_conservacion_total=False,
                                                 incluir_por_validar=False,
                                                 solo_publicables=True, db=db, quien=quien)
    r = limpiar_respuesta(r)
    return {"instrumento": cual,
            "hojas": [h for h in instrumentos.tabla_desde_respuesta(r, buscar, limite)
                      if h["nombre"] != "Instructivo"]}


@router.get("/hoja-de-control/{codigo_carpeta}/datos", summary="Hoja de control para ver en pantalla")
def hoja_de_control_datos(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                          quien: Usuario = Depends(usuario_actual)) -> dict:
    _con_acceso(quien)
    _habilitado(quien, "ve_hojas_control")
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
    if not exp or exp.estado not in CON_HOJA or not es_publicable(db, exp):
        raise HTTPException(404, f"{carpeta} no tiene hoja de control publicada.")
    d = instrumentos.datos_hoja_de_control(db, exp)
    for k in ("fecha_revision", "fecha_diligenciamiento"):
        d[k] = d[k].isoformat() if d.get(k) else ""
    d["tramites"] = [{**t, "fecha": t["fecha"].isoformat() if hasattr(t["fecha"], "isoformat") else (t["fecha"] or "")}
                     for t in d["tramites"]]
    d["carpeta"] = carpeta
    return d


@router.get("/calidad/{codigo_carpeta}", summary="Calidad de las imágenes digitalizadas de una carpeta")
def calidad(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    """Cumplimiento de los criterios de digitalización del PDF que se entrega."""
    _con_acceso(quien)
    _habilitado(quien, "ve_imagenes")
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
    if not exp or exp.estado not in CON_HOJA or not es_publicable(db, exp):
        raise HTTPException(404, f"{carpeta} no está publicada para consulta.")
    from geology.dominio import calidad_imagen
    from geology.rutas.cargue import _archivos_de
    _, rutas = _archivos_de(db, carpeta, entregado=True)
    if not rutas:
        raise HTTPException(404, f"{carpeta} no tiene imágenes digitalizadas publicadas.")
    inf = calidad_imagen.informe_en_cache(carpeta + "_entregado", rutas, exp.volumen_folios)
    return {"carpeta": carpeta, "paginas": inf["paginas"], "formato": inf["formato"],
            "dpi_minimo": inf["dpi_minimo"], "dpi_medio": inf["dpi_medio"],
            "criterios": inf["criterios"], "cumple": inf["cumple"],
            "paginas_a_recapturar": len(inf["sospechosas"])}


def preparar_pdf_consulta(db: Session, exp: Expediente, carpeta: str, parte: int = 0,
                          es_admin: bool = False) -> tuple[str, str]:
    """
    El PDF del tomo completo, unificado, sin metadatos de procesamiento y con los descriptivos
    de archivo. Devuelve (ruta del temporal que quien llama debe borrar, sufijo del nombre).
    La usan la vista de la entidad y el paquete de entrega.
    """
    registros = (db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
                   .order_by(Archivo.fragmento).all())
    if not registros:
        raise HTTPException(404, f"{carpeta} no tiene imágenes digitalizadas publicadas.")

    def _ruta_de(r):
        # La copia de consulta si existe (enderezada, con texto buscable); si no, el original
        # tal como se cargó.
        return next((Path(x) for x in (r.ruta_consulta, r.ruta, r.ruta_matriz)
                     if x and Path(x).exists()), None)

    # La entidad recibe SIEMPRE el libro o tomo completo en un solo PDF: las partes en que se
    # digitalizó (AC-CP-00808_1, _2, _3...) son asunto interno de la producción. Solo la
    # administradora puede pedir una parte suelta, con ?parte=N.
    if parte and es_admin:
        registros = [r for r in registros if r.fragmento == parte]
        if not registros:
            raise HTTPException(404, f"{carpeta} no tiene la parte {parte}.")
    if not (parte and es_admin):
        from geology.dominio import division
        faltan = division.faltantes([r.fragmento for r in registros])
        if faltan:
            raise HTTPException(503, f"El tomo de {carpeta} está incompleto: faltan las partes "
                                     f"{', '.join(map(str, faltan))}. Se entrega cuando esté entero.")
    rutas = [_ruta_de(r) for r in registros]
    if any(r is None for r in rutas):
        raise HTTPException(404, f"Las imágenes de {carpeta} no están disponibles por ahora.")
    sufijo = f"_parte_{parte}" if parte and es_admin else ""
    unido = None
    if len(rutas) > 1:
        unido = unir_pdfs(rutas)
        if unido is None:
            raise HTTPException(503, f"No fue posible unificar las partes de {carpeta} para "
                                     "consulta. Avise a la dirección del proyecto.")
        ruta = Path(unido)
    else:
        ruta = rutas[0]
    limpio = pdf_sin_metadatos(ruta)
    if unido:
        Path(unido).unlink(missing_ok=True)
    if limpio is None:
        # Nunca se entrega el original con sus metadatos: si no se pudo limpiar, no se entrega.
        raise HTTPException(503, f"No fue posible preparar las imágenes de {carpeta} para consulta. "
                                 "Avise a la dirección del proyecto.")
    # Metadatos descriptivos de archivo que pide la guía de digitalización.
    try:
        c = instrumentos._contexto(db, exp)
        con_descriptores(limpio, {
            "Title": f"{carpeta} {nombre_publico(exp)}",
            "Author": (c["periodo"].entidad_productora if c.get("periodo") else ""),
            "Subject": " / ".join(x for x in (c["serie"].nombre if c.get("serie") else "",
                                              c["sub"].nombre if c.get("sub") else "") if x),
            "Keywords": " ".join(x for x in (
                getattr(c.get("seccion"), "codigo_dependencia", "") if c.get("seccion") else "",
                exp.codigo_referencia or "") if x)},
            pdfa=(lambda d: d[0] if len(set(d)) == 1 and d[0] else None)(
                [declaracion_pdfa(r) for r in rutas]))
    except Exception:
        pass
    return limpio, sufijo


@router.get("/ver/{codigo_carpeta}", summary="Imágenes digitalizadas de una carpeta")
def ver(codigo_carpeta: str, parte: int = 0,
        db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    _con_acceso(quien)
    _habilitado(quien, "ve_imagenes")
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
    if not exp or exp.estado not in CON_HOJA or not es_publicable(db, exp):
        raise HTTPException(404, f"{carpeta} no está publicada para consulta.")
    limpio, sufijo = preparar_pdf_consulta(db, exp, carpeta, parte,
                                           quien.rol is Rol.ADMINISTRADORA)
    from starlette.background import BackgroundTask
    return FileResponse(limpio, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{carpeta}{sufijo}.pdf"'},
                        background=BackgroundTask(lambda: Path(limpio).unlink(missing_ok=True)))
