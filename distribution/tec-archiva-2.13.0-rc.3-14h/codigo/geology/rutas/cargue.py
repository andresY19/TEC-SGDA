"""
Cargue de archivos.

Hoy el archivo se sube al servidor y este lo guarda en disco. Cuando se conecte el
almacenamiento de objetos, el navegador subirá directo allá con una dirección prefirmada y
el servidor solo registrará el archivo; el resto de esta capa no cambia.

Lo que sí funciona desde ya, y es lo que evita cargar a ciegas: se reconoce el código de
carpeta del nombre, se comprueba contra el inventario de origen (R3), se detecta el archivo
repetido por su huella (R46) y se registra el expediente en cola con su trazabilidad.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from geology.nucleo.bd import obtener_sesion
from geology.modelos import Archivo, Expediente, Trazabilidad, UnidadInventario
from geology.rutas.cuentas import usuario_actual
from geology.dominio.codigos import partes_de_archivo
from geology.dominio.estados import Estado, Usuario, motivo_de_rechazo_de_carga
from geology.dominio import division

router = APIRouter(prefix="/cargue", tags=["Cargue"])

ALMACEN = Path("deposito")
TROZO = 1024 * 1024
_log = logging.getLogger(__name__)


class _OperacionCargue:
    """Archivos exclusivos y diario de recuperación; no transacción distribuida.

Nunca borra originales completos, partes publicadas ni archivos de operaciones
anteriores. Los errores SQL pueden dejar archivos íntegros sin referencia: el
manifiesto permite conciliarlos, pero no autoriza borrarlos ni reintentar commits.
Una desconexión durante commit se registra como resultado desconocido.
"""

    def __init__(self, almacen: Path, carpeta: str):
        if ".." in almacen.parts or any(p.is_symlink() for p in (almacen, *almacen.parents)):
            raise ValueError("Ruta de depósito insegura.")
        almacen.mkdir(parents=True, exist_ok=True)
        raiz = division._directorio_seguro(almacen)
        operaciones = raiz / "operaciones"
        if operaciones.is_symlink():
            raise ValueError("El directorio de operaciones no puede ser un enlace.")
        operaciones.mkdir(exist_ok=True)
        division._directorio_seguro(operaciones)
        division._sincronizar_directorio(raiz)
        self.directorio = Path(tempfile.mkdtemp(prefix="cargue-", dir=operaciones))
        division._sincronizar_directorio(operaciones)
        self.original = self.directorio / "original.pdf"
        self.manifiesto = self.directorio / "operacion.json"
        self.id = self.directorio.name
        self.datos = {"version": 1, "operacion": self.id, "codigo_carpeta": carpeta,
                      "original": None, "partes": [], "anteriores": [], "registros": [],
                      "commit_intentado": False, "sql_confirmado": False}
        self.estado("recibiendo")

    def estado(self, estado: str, **cambios) -> None:
        datos = {**self.datos, **cambios, "estado": estado,
                 "actualizado_en": datetime.now(timezone.utc).isoformat()}
        if self.manifiesto.is_symlink():
            raise ValueError("Manifiesto de operación inseguro.")
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".diario-",
                                             dir=self.directorio, delete=False) as f:
                temporal = Path(f.name)
                json.dump(datos, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporal, self.manifiesto)
            division._sincronizar_directorio(self.directorio)
            self.datos = datos
        finally:
            if temporal is not None and temporal.exists():
                temporal.unlink()  # Solo el temporal exclusivo creado por esta llamada.

    async def recibir(self, archivo: UploadFile) -> tuple[str, int]:
        temporal = self.directorio / ".original.part"
        identidad = None
        completo = publicado = registrado = False
        h, tamano = hashlib.sha256(), 0
        try:
            with temporal.open("xb") as salida:
                identidad = os.fstat(salida.fileno())
                while True:
                    trozo = await archivo.read(TROZO)
                    if not trozo:
                        break
                    salida.write(trozo)
                    h.update(trozo)
                    tamano += len(trozo)
                salida.flush()
                os.fsync(salida.fileno())
            completo = True
            sha = h.hexdigest()
            self.estado("original_temporal_completo", original_temporal={"ruta": str(temporal),
                        "sha256": sha, "tamano_bytes": tamano})
            division._publicar_atomico(temporal, self.original)
            publicado = True
            division._sincronizar_directorio(self.directorio)
            if division._huella(self.original) != sha:
                raise OSError("No se pudo verificar la integridad del original recibido.")
            self.estado("original_conservado", original={"ruta": str(self.original),
                        "sha256": sha, "tamano_bytes": tamano}, original_temporal=None)
            registrado = True
            return sha, tamano
        finally:
            if identidad is not None and (not completo or (publicado and registrado)):
                try:
                    actual = temporal.lstat()
                    if (actual.st_dev, actual.st_ino) == (identidad.st_dev, identidad.st_ino):
                        temporal.unlink()
                except FileNotFoundError:
                    pass


def _datos_archivo_archivado(archivo) -> dict:
    campos = ("id", "expediente_id", "codigo_carpeta", "fragmento", "nombre_original",
              "ruta", "sha256", "sha256_origen", "tamano_bytes", "ruta_matriz",
              "ruta_consulta", "ruta_texto", "definitiva", "paginas",
              "pagina_inicial", "pagina_final")
    return {c: getattr(archivo, c, None) for c in campos}


def es_el_mismo_fichero(uno: Path, otro: str | Path) -> bool:
    """
    Si dos rutas señalan el mismo fichero del almacén.

    Conservado por compatibilidad. El flujo PDF actual usa directorios exclusivos
    y ya no depende de esta comparación para borrar una carga duplicada.
    """
    try:
        return uno.resolve() == Path(otro).resolve()
    except OSError:
        return str(uno) == str(otro)


def _limpiar(nombre: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nombre.strip())[:120] or "archivo"


@router.post("/cargar", summary="Cargar un expediente digitalizado")
async def cargar(archivo: UploadFile = File(...), db: Session = Depends(obtener_sesion),
                 quien: Usuario = Depends(usuario_actual),
                 reemplazar: bool = Form(False),
                 definitiva: bool = Form(False)) -> dict:
    """
    Con reemplazar=true las imágenes nuevas sustituyen a las ya cargadas de esa carpeta (o
    solo de esa parte, si el nombre trae número de parte) y la HOJA DE CONTROL SE CONSERVA:
    no se vuelve a leer ni se pierde ninguna edición. Es para cambiar las fotos de cámara
    por las del escáner definitivo. Queda constancia con la huella de lo que se retiró.
    """
    return await cargar_documento(archivo, db, quien, reemplazar, definitiva)


async def cargar_documento(archivo, db, quien, reemplazar=False, definitiva=False, *, sync_commit=None):
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no carga expedientes.")

    partes = partes_de_archivo(archivo.filename or "")
    if not partes.carpeta:
        raise HTTPException(422, f"El nombre «{archivo.filename}» no permite deducir el código de "
                                 "carpeta. Renómbrelo como AC-CP-00374.pdf, o CARPETA_00374.pdf.")
    carpeta = partes.carpeta

    unidad = (db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == carpeta)
              .with_for_update().first())
    if not unidad:
        raise HTTPException(422, f"La carpeta {carpeta} no está en el inventario de origen del "
                                 "contrato, es decir no pertenece a la selección inventariada.")

    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()

    # Un expediente se carga entero o por partes, nunca de las dos maneras a la vez: si ya
    # hay partes registradas no entra un archivo entero, y si ya está el entero no entra una
    # parte suelta. Mezclarlos haría que la lectura tomara el mismo papel dos veces.
    todos = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all()
    existentes = [a for a in todos if Path(a.ruta).is_file()]
    viejos = [a for a in existentes if not partes.es_fragmento or a.fragmento == partes.fragmento]
    reemplazar = bool(reemplazar is True) and bool(viejos)
    definitiva = definitiva is True
    if reemplazar:
        # Sustituir no es duplicar: se saltan los guardianes de «ya cargada».
        pass
    elif existentes and not partes.es_fragmento and any(a.fragmento > 0 for a in existentes):
        raise HTTPException(409, f"{carpeta} ya está cargada por partes "
                                 f"({len(existentes)} archivo(s)). Cargue la parte que falte con su "
                                 "número (por ejemplo CARPETA-00001-4.pdf) o retire el expediente "
                                 "para volver a cargarlo entero.")
    if not reemplazar and existentes and partes.es_fragmento and any(
            a.fragmento == 0 for a in existentes):
        raise HTTPException(409, f"{carpeta} ya está cargada completa en un solo archivo. Si el "
                                 "expediente viene por partes, retire el expediente y cargue "
                                 "todas las partes numeradas.")

    if (partes.es_fragmento and not reemplazar
            and any(a.fragmento == partes.fragmento for a in existentes)):
        raise HTTPException(409, "Esta parte ya está cargada; use reemplazar para sustituirla.")

    if existentes and not partes.es_fragmento and not reemplazar:
        raise HTTPException(409, f"{carpeta} ya tiene imágenes cargadas. Si son las definitivas "
                                 "(por ejemplo las del escáner en lugar de las fotos), marque "
                                 "«Reemplazar las imágenes ya cargadas»: la hoja de control se "
                                 "conserva.")
    if exp and not partes.es_fragmento and not reemplazar:
        from geology.dominio.estados import Expediente as ExpedienteCalculo
        rechazo = motivo_de_rechazo_de_carga(
            ExpedienteCalculo(exp.codigo_carpeta, Estado(exp.estado), describio=exp.describio))
        if rechazo:
            raise HTTPException(409, rechazo)

    # Serializa cargues de esta carpeta mediante la fila de inventario existente.
    # No hay transacción distribuida: los archivos íntegros se conservan incluso
    # cuando SQL falla. El diario identifica los que requieren conciliación.
    operacion = _OperacionCargue(ALMACEN, carpeta)
    commit_intentado = False
    try:
        sha, tamano = await operacion.recibir(archivo)
        destino = operacion.original
        if reemplazar and any(a.sha256 == sha or a.sha256_origen == sha for a in viejos):
            raise HTTPException(409, "El documento es idéntico al que ya está cargado; se conservó sin reemplazar.")
        from sqlalchemy import or_ as _or
        repetidos = db.query(Archivo).filter(_or(Archivo.sha256 == sha, Archivo.sha256_origen == sha)).all()
        if any(Path(a.ruta).is_file() for a in repetidos):
            raise HTTPException(409, "DUPLICADO. El documento ya está registrado; no se modificó el archivo anterior.")

        from geology.dominio.recepcion_tecnica import leer_ficha
        ficha = leer_ficha(destino)
        if ficha.error or not ficha.paginas or ficha.sha256 != sha:
            raise HTTPException(422, "No se pudo verificar el PDF recibido; el original se conserva para revisión.")
        cortadas = []
        # Reemplazar el documento completo retira lógicamente todas sus partes;
        # reemplazar una parte conserva las restantes y no vuelve a dividirla.
        restantes = [] if reemplazar and not partes.es_fragmento else existentes
        if (not partes.es_fragmento and division.hay_que_dividir(ficha.paginas)
                and not any(a.fragmento > 0 for a in restantes)):
            operacion.estado("division_en_curso", paginas=ficha.paginas,
                             paginas_por_parte=division.PAGINAS_POR_PARTE)
            cortadas = division.dividir(destino, carpeta, operacion.directorio,
                                        "documento.pdf")
            division.validar_partes(cortadas, operacion.directorio, ficha.paginas)
        registros = []
        for parte in cortadas:
            ficha_parte = leer_ficha(parte.ruta)
            if ficha_parte.error or ficha_parte.sha256 != parte.sha256 or ficha_parte.paginas != parte.paginas:
                raise HTTPException(422, "Una parte no superó la verificación técnica; no se persistió la división.")
            registros.append(Archivo(
                expediente_id=exp.id if exp else None, codigo_carpeta=carpeta, fragmento=parte.numero,
                nombre_original=f"{archivo.filename} (parte {parte.numero}, páginas {parte.pagina_inicial}-{parte.pagina_final})",
                ruta=str(parte.ruta), tamano_bytes=parte.tamano_bytes, sha256=parte.sha256,
                sha256_origen=sha, subido_por=quien.nombre, paginas=parte.paginas,
                dpi_minimo=ficha_parte.dpi_minimo, dpi_medio=ficha_parte.dpi_medio,
                bits_por_color=ficha_parte.bits_por_color,
                tiene_capa_de_texto=ficha_parte.tiene_capa_de_texto,
                avisos_tecnicos=" | ".join(ficha_parte.avisos) or None,
                pagina_inicial=parte.pagina_inicial, pagina_final=parte.pagina_final,
                dividido_por_sistema=True, definitiva=definitiva))
        if not registros:
            registros.append(Archivo(
                expediente_id=exp.id if exp else None, codigo_carpeta=carpeta, fragmento=partes.fragmento,
                nombre_original=archivo.filename or "", ruta=str(destino), tamano_bytes=tamano,
                sha256=sha, subido_por=quien.nombre, paginas=ficha.paginas,
                dpi_minimo=ficha.dpi_minimo, dpi_medio=ficha.dpi_medio,
                bits_por_color=ficha.bits_por_color, tiene_capa_de_texto=ficha.tiene_capa_de_texto,
                avisos_tecnicos=" | ".join(ficha.avisos) or None, definitiva=definitiva))
        fantasmas = [a for a in todos if not Path(a.ruta).is_file()]
        anteriores = (viejos if reemplazar else []) + fantasmas
        operacion.estado("archivos_verificados", partes=[_datos_archivo_archivado(a) for a in registros],
                         anteriores=[_datos_archivo_archivado(a) for a in anteriores])

        # No se ejecutan deletes ni inserts hasta verificar TODOS los archivos.
        for a in anteriores:
            db.delete(a)  # Solo filas de esta carpeta; los archivos anteriores se conservan.
        if anteriores:
            # Orden explícito para posibles restricciones únicas del esquema original.
            # Sigue dentro de la transacción: rollback restaura estas referencias.
            db.flush()
        if reemplazar and exp:
            retirados = "; ".join(f"parte {a.fragmento or 'única'}: {a.nombre_original} (SHA-256 {a.sha256})" for a in viejos)
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                                estado_nuevo=exp.estado, accion="reemplazar_imagenes", usuario=quien.nombre,
                                motivo=f"Operación {operacion.id}. Se sustituyeron referencias de imágenes. "
                                       f"Los archivos previos se conservan: {retirados}. La hoja se conserva."))
        if exp and exp.estado == Estado.DEVUELTO.value and not reemplazar:
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                                estado_nuevo=Estado.EN_COLA.value, accion="cargar", usuario=quien.nombre,
                                motivo=f"Documento recibido; operación {operacion.id}."))
            exp.estado = Estado.EN_COLA.value
        if not exp:
            exp = Expediente(codigo_carpeta=carpeta, estado=Estado.EN_COLA.value,
                             caja_origen=unidad.caja_origen, caja_trabajo=unidad.caja_trabajo,
                             responsable=quien.nombre, archivo_origen=archivo.filename)
            db.add(exp)
            db.flush()
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=None,
                                estado_nuevo=Estado.EN_COLA.value, accion="cargar", usuario=quien.nombre,
                                motivo=f"Documento recibido; operación {operacion.id}."))
        for r in registros:
            r.expediente_id = exp.id
        db.add_all(registros)
        db.flush()
        division_hecha = None
        if cortadas:
            division_hecha = (f"Operación {operacion.id}: {ficha.paginas} páginas en {len(cortadas)} partes. "
                              f"Original conservado: {destino}. SHA-256 {sha}.")
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                                estado_nuevo=exp.estado, accion="dividir_documento",
                                usuario=quien.nombre, motivo=division_hecha))
        if ficha.avisos:
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                                estado_nuevo=exp.estado, accion="recepcion_tecnica", usuario=quien.nombre,
                                motivo=" ".join(ficha.avisos)))
        fragmentos = [a.fragmento for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all()]
        faltan = division.faltantes(fragmentos)
        if faltan:
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                                estado_nuevo=exp.estado, accion="secuencia", usuario=quien.nombre,
                                motivo=f"Faltan las partes {', '.join(map(str, faltan))} de {carpeta}."))
        # Última comprobación inmediatamente antes de intentar el commit.
        if division._huella(destino) != sha:
            raise OSError("El original cambió antes de la confirmación SQL.")
        if cortadas:
            division.validar_partes(cortadas, operacion.directorio, ficha.paginas)
        for r in registros:
            if Path(r.ruta).stat().st_size != r.tamano_bytes or division._huella(Path(r.ruta)) != r.sha256:
                raise OSError("Un archivo cambió antes de la confirmación SQL.")
        operacion.estado("confirmacion_sql_pendiente", commit_intentado=True,
                         registros=[_datos_archivo_archivado(a) for a in registros])
        if sync_commit is not None:
            sync_commit(exp, sha)
        commit_intentado = True
        db.commit()
    except BaseException as error:
        rollback_confirmado = False
        try:
            db.rollback()
            rollback_confirmado = True
        except Exception:
            _log.error("No se pudo completar el rollback del cargue; requiere conciliación.")
        try:
            estado_fallo = ("resultado_sql_desconocido" if commit_intentado else
                            "revertida_antes_commit" if rollback_confirmado else "rollback_no_confirmado")
            operacion.estado(estado_fallo, rollback_confirmado=rollback_confirmado,
                             commit_intentado=commit_intentado, requiere_conciliacion=True,
                             tipo_error=type(error).__name__)
        except Exception:
            _log.error("No se pudo actualizar el diario de cargue; se conservan los archivos.")
        # No se eliminan originales ni partes: commit puede haber sido aplicado
        # aunque la conexión haya fallado antes de devolver la respuesta.
        if isinstance(error, HTTPException):
            raise
        if isinstance(error, Exception):
            raise HTTPException(503, f"Cargue no confirmado. Operación {operacion.id}; conserve el identificador para conciliación.") from None
        raise
    aviso_integridad = ""
    try:
        operacion.estado("confirmada", sql_confirmado=True, requiere_conciliacion=False)
    except Exception:
        aviso_integridad = f"SQL confirmado; diario pendiente de conciliación para {operacion.id}."
        _log.error("SQL confirmado, pero no se pudo actualizar el diario del cargue.")
    levantado, validacion, aviso_periodo, partes_cargadas = _tras_confirmar_cargue(
        db, exp, registros, carpeta, reemplazar, quien)
    return {
        "operacion_cargue": operacion.id,
        "original_conservado": str(operacion.original),
        "sha256_original": sha,
        "aviso_integridad": aviso_integridad,
        "aviso_periodo": aviso_periodo,
        "validacion": validacion,
        "carpeta": carpeta,
        "fragmento": partes.fragmento,
        "partes_cargadas": partes_cargadas,
        "dividido_por_sistema": bool(division_hecha),
        "partes_del_sistema": [{"parte": r.fragmento, "paginas": f"{r.pagina_inicial}-{r.pagina_final}"}
                               for r in registros] if division_hecha else [],
        "partes_faltantes": faltan,
        "estado": exp.estado,
        "tamano_mb": round(tamano / 1048576, 2),
        "periodo_inventario": unidad.periodo or "sin periodo (S/F)",
        "folios_inventario": unidad.folios,
        "asunto_inventario": unidad.asunto,
        "caja_origen": unidad.caja_origen,
        "ficha_tecnica": ficha.como_dict(),
        "levantamiento_automatico": levantado,
        "reemplazo": bool(reemplazar),
        "definitiva": definitiva,
        "mensaje": (f"Expediente {carpeta} registrado. El modelo empieza a leerlo en unos "
                    "segundos y la hoja de control aparecerá diligenciada en «Hojas de control»."
                    if levantado else
                    f"Expediente {carpeta} registrado en cola. Diligencie su hoja de control en "
                    "la pestaña Hojas de control."),
    }



def _tras_confirmar_cargue(db, exp, registros, carpeta, reemplazar, quien):
    # La matriz de preservación y la copia de consulta se construyen en segundo plano: son
    # pesadas y no tienen por qué hacer esperar a quien está cargando.
    for r in registros:
        try:
            from geology.trabajos import preparar_digitalizacion
            preparar_digitalizacion.delay(r.id)
        except Exception as e:
            print(f"AVISO. No se pudo encolar la preparación del archivo {r.id}: {e}")

    # Y el levantamiento de la hoja de control arranca solo. Nadie tiene que pulsar nada: se
    # sube la carpeta y el modelo empieza a leerla.
    #
    # Se espera un poco antes de empezar. Un expediente partido llega como _1, _2 y _3 con
    # segundos de diferencia, y la tarea lee TODAS las partes que encuentre: sin esa espera se
    # leería tres veces, la primera con una sola parte. La espera se cambia con SEGUNDOS_ANTES
    # _DE_LEER y el arranque automático se apaga con LEVANTAR_AL_CARGAR=no.
    levantado = False
    if (not reemplazar
            and os.getenv("LEVANTAR_AL_CARGAR", "si").strip().lower() not in ("no", "0", "false")):
        if exp.estado in (Estado.EN_COLA.value, Estado.DEVUELTO.value,
                          Estado.HOJA_EN_ELABORACION.value):
            try:
                from geology.modelos import Trazabilidad as _T
                turno = (db.query(func.count(_T.id))
                           .filter(_T.accion == "levantar_hoja").scalar() or 0)
                from geology.trabajos import levantar_hoja_de_control
                levantar_hoja_de_control.apply_async(
                    args=[exp.id, quien.nombre, turno],
                    countdown=int(os.getenv("SEGUNDOS_ANTES_DE_LEER", "45")))
                levantado = True
            except Exception as e:
                print(f"AVISO. No se pudo encolar el levantamiento de {carpeta}: {e}")

    partes_cargadas = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).count()
    # Si la carpeta ya tiene hoja de control, se contrasta de una vez con la imagen que acaba
    # de llegar y se dice en pantalla si algo no cuadra.
    validacion = None
    try:
        from geology.dominio.validar_entrega import validar_unidad
        db.refresh(exp)
        if exp.tramites:
            validacion = validar_unidad(db, exp)
    except Exception as e:
        print(f"AVISO. No se pudo validar {carpeta} contra la imagen: {e}")
    aviso_periodo = ""
    try:
        from geology.dominio import planeacion as _pl
        aviso_periodo = _pl.aviso_de_salto(_pl.construir(db, True), carpeta)
    except Exception as e:
        print(f"AVISO. No se pudo comprobar el periodo de {carpeta}: {e}")
    return levantado, validacion, aviso_periodo, partes_cargadas


def _cuerpo_de(h, e: dict, nombre: str, quien, verificar: bool):
    """
    Arma la hoja de control a partir de lo que se leyó del libro.

    Va en su propia función para poder envolverla: aquí es donde cada casilla se comprueba, y
    una sola que no pase —un número donde iba texto, un campo más largo de lo que admite—
    levantaba una excepción que tumbaba la carga entera del lote sin decir cuál hoja fue.
    """
    from geology.rutas.unidades import HojaDeControl, TramiteEntrada
    return HojaDeControl(
        codigo_carpeta=h.codigo_carpeta, archivo_origen=nombre,
        codigo_serie=e.get("codigo_serie", ""), serie=e.get("serie", ""),
        codigo_subserie=e.get("codigo_subserie", ""), subserie=e.get("subserie", ""),
        nombre_expediente=e.get("nombre_expediente", ""),
        responsable=quien.nombre,
        fecha_diligenciamiento=e.get("fecha_diligenciamiento", ""),
        periodo_manual=e.get("periodo") or None,
        modo="verificar" if verificar else "avance",
        tramites=[TramiteEntrada(
            no_item=int(t["no_item"]) if str(t.get("no_item", "")).strip().isdigit() else None,
            fecha=t.get("fecha") or None, tipo_documental=t.get("tipo_documental", ""),
            folio_desde=t.get("folio_desde") or None, folio_hasta=t.get("folio_hasta") or None,
            no_radicado=t.get("no_radicado", ""),
            sistema_informacion=t.get("sistema_informacion", ""),
            expediente_sgdea=t.get("expediente_sgdea", ""),
            enlace_acceso=t.get("enlace_acceso", ""),
            observaciones=t.get("observaciones", ""), fila=t.get("fila"))
            for t in h.tramites])


@router.post("/hoja-de-control", summary="Importar hojas de control diligenciadas en Excel")
async def importar_hoja(archivo: UploadFile = File(...), verificar: bool = True,
                        db: Session = Depends(obtener_sesion),
                        quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Sube un libro de cálculo con una o varias hojas de control ya diligenciadas y las mete al
    flujo, verificándolas con las mismas reglas que las que se diligencian aquí.

    El trabajo hecho fuera de la plataforma no se vuelve a escribir: se importa y se le hace
    calidad. Lo que esté mal sale señalado con el número del trámite y la fila del Excel.
    """
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no carga hojas de control.")

    nombre = archivo.filename or "hoja.xlsx"
    if not nombre.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, f"«{nombre}» no es un libro de cálculo. Se admiten .xlsx y .xlsm.")

    # Excel se valida en memoria, sin reemplazar archivos anteriores.
    contenido = bytearray()
    while True:
        trozo = await archivo.read(TROZO)
        if not trozo:
            break
        contenido.extend(trozo)
        if len(contenido) > 25 * 1024 * 1024:
            raise HTTPException(413, "El libro supera el límite local de 25 MiB.")

    from geology.rutas.unidades import guardar_hoja
    from geology.dominio.importar_hoja import leer_libro

    resultados = []

    # Leer el libro va aparte y con su propia red: un archivo dañado, protegido con
    # contraseña o con una hoja que openpyxl no entienda no puede llegar a la pantalla como
    # «Internal Server Error», que es un mensaje que no le sirve a nadie.
    try:
        hojas = leer_libro(bytes(contenido), nombre)
    except Exception as ex:
        raise HTTPException(422, (
            f"No se pudo leer «{nombre}» ({type(ex).__name__}). Suele pasar cuando el "
            "archivo quedó a medio descargar, está protegido con contraseña, o se guardó en "
            "un formato que no es el actual de Excel. Ábralo, use «Guardar como» → Libro de "
            f"Excel (*.xlsx) y vuelva a subirlo. Detalle: {str(ex)[:180]}"))

    if not hojas or any(h.error or not h.codigo_carpeta or not h.tramites for h in hojas):
        raise HTTPException(422, "Libro incompleto; no se guardó ninguna hoja.")
    try:
        cuerpos = [_cuerpo_de(h, h.encabezado, nombre, quien, verificar) for h in hojas]
    except (ValueError, TypeError) as ex:
        raise HTTPException(422, "Datos incompatibles con la hoja de control; no se guardó ninguna hoja.") from ex

    # Un orden estable reduce conflictos al importar libros con carpetas en común.
    try:
        for h, cuerpo in sorted(zip(hojas, cuerpos), key=lambda par: par[0].codigo_carpeta):
            r = guardar_hoja(cuerpo, db, quien, confirmar=False)
            r["hoja"] = h.hoja
            r["avisos_de_lectura"] = h.avisos
            resultados.append(r)
        db.commit()
    except HTTPException as ex:
        db.rollback()
        raise HTTPException(ex.status_code, f"No se importó el libro. Hoja {h.hoja}: {ex.detail}") from ex
    except Exception:
        db.rollback()
        raise

    por_hoja = {r["hoja"]: r for r in resultados}
    resultados = [por_hoja[h.hoja] for h in hojas]
    from geology.dominio.validar_entrega import validar_unidad
    for r in resultados:
        try:
            exp = db.query(Expediente).filter(Expediente.codigo_carpeta == r["carpeta"]).first()
            r["validacion"] = validar_unidad(db, exp) if exp else None
        except Exception:
            db.rollback()
            r["validacion"] = None

    con_errores = sum(1 for r in resultados if r.get("errores"))
    con_dif_imagen = sum(1 for r in resultados
                         if r.get("validacion") and r["validacion"]["errores"])
    return {
        "con_diferencias_con_imagen": con_dif_imagen,
        "archivo": nombre,
        "hojas_leidas": len(resultados),
        "importadas": len(resultados),
        "con_errores": con_errores,
        "rechazadas": [],
        "resultados": resultados,
        "mensaje": (f"{len(resultados)} hoja(s) importada(s); {con_errores} con errores por "
                    "corregir."),
    }


_IMAGENES = (".jpg", ".jpeg", ".png", ".tif", ".tiff")


def _natural(nombre: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", nombre or "")]


@router.post("/cargar-imagenes", summary="Cargar un expediente digitalizado como imágenes")
async def cargar_imagenes(imagenes: list[UploadFile] = File(...), nombre: str = Form(...),
                          reemplazar: bool = Form(False), definitiva: bool = Form(False),
                          db: Session = Depends(obtener_sesion),
                          quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Une las imágenes (JPG, PNG, TIFF) en un solo PDF, en el orden natural de sus nombres, y
    lo carga como cualquier otro documento. La unión no recomprime: el JPEG viaja tal cual
    dentro del PDF, así que no se pierde calidad ni resolución. Si la imagen no trae su
    resolución escrita, la ficha técnica lo dirá en lugar de suponerla.
    """
    import io
    import img2pdf
    from starlette.datastructures import Headers
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no carga expedientes.")
    if not imagenes:
        raise HTTPException(422, "No llegó ninguna imagen.")
    malas = [i.filename for i in imagenes if not (i.filename or "").lower().endswith(_IMAGENES)]
    if malas:
        raise HTTPException(422, "Solo se unen imágenes JPG, PNG o TIFF. No sirven: "
                                 + ", ".join(malas[:5]))
    nombre = re.sub(r"\.(pdf|jpe?g|png|tiff?)$", "", (nombre or "").strip(), flags=re.I)
    if not partes_de_archivo(nombre + ".pdf"):
        raise HTTPException(422, f"El nombre «{nombre}» no permite deducir el código de carpeta.")
    orden = sorted(imagenes, key=lambda i: _natural(i.filename))
    datos = [await i.read() for i in orden]
    try:
        pdf = img2pdf.convert(datos)
    except Exception:
        # Una PNG con transparencia o una TIFF rara: se pasa por Pillow a RGB y se reintenta.
        from PIL import Image
        convertidas = []
        for d in datos:
            im = Image.open(io.BytesIO(d))
            dpi = im.info.get("dpi")
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=100, subsampling=0, dpi=dpi or (0, 0))
            convertidas.append(buf.getvalue())
        pdf = img2pdf.convert(convertidas)
    envoltorio = UploadFile(file=io.BytesIO(pdf), filename=nombre + ".pdf",
                            headers=Headers({"content-type": "application/pdf"}))
    r = await cargar(envoltorio, db, quien, reemplazar=bool(reemplazar is True),
                     definitiva=bool(definitiva is True))
    r["imagenes_unidas"] = len(orden)
    return r


def _archivos_de(db, carpeta: str, entregado: bool = False):
    regs = (db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
              .order_by(Archivo.fragmento).all())
    rutas = []
    for a in regs:
        cand = ([a.ruta_consulta, a.ruta, a.ruta_matriz] if entregado
                else [a.ruta, a.ruta_matriz, a.ruta_consulta])
        r = next((Path(x) for x in cand if x and Path(x).exists()), None)
        if r:
            rutas.append(r)
    return regs, rutas


@router.get("/calidad/{codigo_carpeta}", summary="Control de calidad de la digitalización")
def calidad(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    from geology.dominio import calidad_imagen
    from geology.dominio.codigos import normalizar_codigo_carpeta
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    regs, rutas = _archivos_de(db, carpeta)
    if not rutas:
        raise HTTPException(404, f"{carpeta} no tiene imágenes cargadas.")
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
    folios = exp.volumen_folios if exp else None
    return {"carpeta": carpeta,
            **calidad_imagen.informe_en_cache(carpeta, rutas, folios)}


@router.get("/calidad/{codigo_carpeta}/excel", summary="Informe de calidad en Excel")
def calidad_excel(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)):
    from fastapi.responses import Response
    inf = calidad(codigo_carpeta, db, quien)
    from geology.dominio import calidad_imagen
    datos = calidad_imagen.informe_en_excel(inf["carpeta"], inf)
    return Response(datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition":
                             f'attachment; filename="Calidad_{inf["carpeta"]}.xlsx"'})


@router.get("/ver/{codigo_carpeta}", summary="El documento digitalizado, para verlo en pantalla")
def ver_documento(codigo_carpeta: str, parte: int = 0, copia: str = "original",
                  db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)):
    """
    Devuelve el expediente digitalizado para poder mirarlo mientras se corrige la hoja.

    Corregir una foliación o una fecha sin tener el papel a la vista es adivinar. Hasta ahora
    había que salir de la plataforma, buscar el archivo en el disco del servidor y abrirlo
    aparte; con esto se abre al lado de la hoja.

    Se puede pedir la copia de consulta, que está enderezada y con texto buscable, o el
    original tal como se cargó. Por omisión va el original, porque es contra el original que
    se comprueba lo que dice la hoja.
    """
    from fastapi.responses import FileResponse

    from geology.dominio.codigos import normalizar_codigo_carpeta

    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    consulta = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
    if parte:
        consulta = consulta.filter(Archivo.fragmento == parte)
    registro = consulta.order_by(Archivo.fragmento).first()
    if not registro:
        raise HTTPException(404, f"{carpeta} no tiene ningún documento cargado.")

    candidatas = []
    if copia == "consulta" and registro.ruta_consulta:
        candidatas.append(registro.ruta_consulta)
    candidatas += [registro.ruta, registro.ruta_matriz, registro.ruta_consulta]
    ruta = next((Path(r) for r in candidatas if r and Path(r).exists()), None)
    if not ruta:
        raise HTTPException(404, f"El archivo de {carpeta} figura cargado pero no está en el "
                                 "almacén del servidor. Vuelva a subirlo en la pantalla de Cargue.")

    return FileResponse(ruta, media_type="application/pdf",
                        headers={"Content-Disposition":
                                 f'inline; filename="{carpeta}.pdf"'})


@router.get("/partes/{codigo_carpeta}", summary="Cuántas partes tiene el expediente")
def partes_del_expediente(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                          quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    """Los archivos de una carpeta, para poder pasar de una parte a otra en el visor."""
    from geology.dominio.codigos import normalizar_codigo_carpeta
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    return [{"fragmento": a.fragmento, "nombre": a.nombre_original,
             "paginas": a.paginas, "en_disco": Path(a.ruta).exists(),
             "tiene_copia_de_consulta": bool(a.ruta_consulta and Path(a.ruta_consulta).exists())}
            for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
                       .order_by(Archivo.fragmento).all()]


@router.get("/estado-de-cargas",
            summary="Todo lo que se ha subido y en qué va cada cosa")
def estado_de_cargas(db: Session = Depends(obtener_sesion),
                     quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    El recuento de todo lo cargado, para poder responder la pregunta que importa cuando se
    lleva días subiendo carpetas: ¿se perdió algo?

    Se cruzan tres cosas que hasta ahora solo se miraban por separado y por eso nadie sabía
    si cuadraban: lo que hay REGISTRADO en la base, lo que hay de verdad EN EL DISCO del
    servidor, y en qué ESTADO va cada expediente.

    De ese cruce salen las tres formas en que algo se puede «perder», y conviene distinguirlas
    porque se arreglan distinto:

      · Registrado pero sin archivo. El expediente figura cargado y el archivo no está en el
        almacén. Pasa cuando se reinstaló el contenedor sin conservar la carpeta, o cuando
        una carga quedó a medias. Se resuelve volviendo a subir ese archivo.
      · Archivo sin registrar. El documento está en el disco pero no le corresponde ningún
        expediente. Pasa cuando alguien copia archivos a mano a la carpeta del almacén en vez
        de subirlos por la plataforma. Se resuelve subiéndolo por la pantalla de Cargue.
      · Cargado pero sin leer. El archivo está y el expediente existe, pero nadie ha levantado
        su hoja de control. No está perdido: está esperando turno.
    """
    from geology.dominio.estados import Estado as E

    archivos = db.query(Archivo).order_by(Archivo.codigo_carpeta, Archivo.fragmento).all()
    expedientes = {e.codigo_carpeta: e for e in db.query(Expediente).all()}

    # Cuántos trámites tiene levantados cada expediente, en una sola consulta.
    from geology.modelos import Tramite
    conteo = dict(db.query(Tramite.expediente_id, func.count(Tramite.id))
                    .group_by(Tramite.expediente_id).all())

    detalle = []
    en_disco = faltan = 0
    rutas_registradas = set()

    for a in archivos:
        ruta = Path(a.ruta)
        existe = ruta.exists()
        rutas_registradas.add(ruta.name)
        if existe:
            en_disco += 1
        else:
            faltan += 1
        exp = expedientes.get(a.codigo_carpeta)
        ultimo = ""
        if exp and exp.trazabilidad:
            ultimo = (exp.trazabilidad[-1].motivo or "")[:160]
        detalle.append({
            "carpeta": a.codigo_carpeta,
            "archivo": a.nombre_original,
            "fragmento": a.fragmento,
            "mb": round((a.tamano_bytes or 0) / 1048576, 2),
            "paginas": a.paginas,
            "subido_por": a.subido_por or "",
            "subido_en": a.subido_en.isoformat(timespec="minutes") if a.subido_en else "",
            "en_disco": existe,
            "estado": exp.estado if exp else "sin expediente",
            "tramites": conteo.get(exp.id, 0) if exp else 0,
            "folios": (exp.volumen_folios if exp else None),
            "ultimo_movimiento": ultimo,
            "que_hacer": _que_hacer(existe, exp, conteo.get(exp.id, 0) if exp else 0),
        })

    # Lo que está en el disco y nadie registró.
    huerfanos = []
    if ALMACEN.exists():
        for ruta in sorted(ALMACEN.glob("*.pdf")) + sorted(ALMACEN.glob("*.PDF")):
            if ruta.name not in rutas_registradas:
                huerfanos.append({"archivo": ruta.name,
                                  "mb": round(ruta.stat().st_size / 1048576, 2),
                                  "que_hacer": "Está en el disco pero no se registró. Súbalo "
                                               "por la pantalla de Cargue para que entre al flujo."})

    fechas = sorted(d["subido_en"] for d in detalle if d["subido_en"])
    sin_leer = sum(1 for d in detalle if d["en_disco"] and d["tramites"] == 0)
    carpetas = {d["carpeta"] for d in detalle}
    terminadas = sum(1 for c in carpetas
                     if c in expedientes and expedientes[c].estado in
                     (E.ARCHIVADO.value, E.EN_INVENTARIO.value))

    return {
        "resumen": {
            "archivos_cargados": len(archivos),
            "carpetas_distintas": len(carpetas),
            "en_disco": en_disco,
            "faltan_en_disco": faltan,
            "sin_registrar": len(huerfanos),
            "sin_leer": sin_leer,
            "terminadas": terminadas,
            # Entre qué fechas se subió todo esto. Es lo que permite decir «el sistema tiene
            # esto» en una frase, sin tener que recorrer la lista.
            "primera_carga": fechas[0] if fechas else "",
            "ultima_carga": fechas[-1] if fechas else "",
            "folios_registrados": sum((expedientes[c].volumen_folios or 0)
                                      for c in carpetas if c in expedientes),
        },
        "detalle": detalle,
        "huerfanos": huerfanos,
    }


def _que_hacer(existe: bool, exp, tramites: int) -> str:
    """Una frase por renglón que diga qué sigue, sin obligar a interpretar el estado."""
    from geology.dominio.estados import Estado as E
    if not exp:
        return ("El archivo está registrado pero no le corresponde ningún expediente. "
                "Vuelva a subirlo por la pantalla de Cargue.")
    if not existe:
        return ("El archivo NO está en el almacén del servidor. Vuelva a subirlo en Cargue: "
                "el registro se reemplaza y no se duplica.")
    if exp.estado == E.EN_PROCESAMIENTO.value:
        return "El modelo lo está leyendo en este momento. Espere."
    if exp.estado == E.DEVUELTO.value:
        return "Tiene errores señalados. Ábralo en Hojas de control y corrija."
    if tramites == 0:
        return "Está cargado pero nadie ha levantado su hoja. Pulse «Levantar con el modelo»."
    if exp.estado == E.HOJA_EN_ELABORACION.value:
        return "El modelo propuso la hoja. Revísela y pulse «Guardar y verificar»."
    if exp.estado == E.HOJA_POR_REVISAR.value:
        return "Espera que una persona la revise y pulse «Marcar revisada»."
    if exp.estado == E.HOJA_REVISADA.value:
        return "Lista para generar el ISAD(G)."
    if exp.estado == E.DESCRIPCION_POR_VALIDAR.value:
        return "Espera validación de la descripción."
    if exp.estado == E.DESCRIPCION_VALIDADA.value:
        return "Espera aprobación de la dirección o la líder."
    if exp.estado == E.ARCHIVADO.value:
        return "Aprobada. Falta asignarle caja definitiva en Reubicación."
    if exp.estado == E.EN_INVENTARIO.value:
        return "Terminada: ya está en el inventario de salida."
    return "En cola."


@router.get("/de/{codigo_carpeta}", summary="Archivos cargados de una carpeta")
def de_carpeta(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    carpeta = (partes_de_archivo(codigo_carpeta).carpeta or codigo_carpeta.upper())
    return [{"nombre": a.nombre_original, "parte": a.fragmento,
             "tamano_mb": round(a.tamano_bytes / 1048576, 2),
             "subido_por": a.subido_por, "subido_en": a.subido_en.isoformat(timespec="minutes")}
            for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
                       .order_by(Archivo.fragmento).all()]
