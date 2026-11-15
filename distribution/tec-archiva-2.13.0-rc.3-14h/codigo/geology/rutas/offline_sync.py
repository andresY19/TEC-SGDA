"""Development-only offline create protocol using the certified document ingest."""
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from geology.dominio.estados import Estado, Rol, Usuario
from geology.modelos import Archivo, Expediente, UnidadInventario
from geology.nucleo.bd import obtener_sesion
from geology.rutas.cargue import ALMACEN, cargar_documento
from geology.rutas.cuentas import usuario_actual
from geology.rutas.unidades import HojaDeControl, TramiteEntrada, guardar_hoja, trazabilidad

router = APIRouter(prefix='/offline/v1')
LIMIT = 16 * 1024 * 1024
EDITABLE = {Estado.EN_COLA.value, Estado.HOJA_EN_ELABORACION.value}


def authorized(user: Usuario = Depends(usuario_actual)) -> Usuario:
    if os.getenv('GEOLOGY_OFFLINE_DEV') != '1':
        raise HTTPException(404)
    if user.rol is not Rol.ADMINISTRADORA or not user.edita_hoja_control:
        raise HTTPException(403, 'Perfil sin habilitación offline en este piloto.')
    return user


def version(unit, expedition):
    fields = [unit.codigo_carpeta, unit.periodo, unit.folios, unit.asunto,
              unit.caja_origen, unit.caja_trabajo]
    if expedition:
        fields += [expedition.id, expedition.estado, str(expedition.actualizado_en)]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


@router.get('/snapshot')
def snapshot(user: Usuario = Depends(authorized), db: Session = Depends(obtener_sesion)):
    values = db.query(UnidadInventario, Expediente).outerjoin(
        Expediente, UnidadInventario.codigo_carpeta == Expediente.codigo_carpeta
    ).order_by(UnidadInventario.codigo_carpeta).limit(200).all()
    documents = db.query(Archivo).filter(
        Archivo.codigo_carpeta.in_([u.codigo_carpeta for u, _ in values])
    ).order_by(Archivo.id).all()
    by_code = {}
    for item in documents:
        by_code.setdefault(item.codigo_carpeta, []).append({
            'id': item.id, 'name': item.nombre_original, 'sha256': item.sha256,
            'bytes': item.tamano_bytes})
    return {'owner': user.correo, 'items': [
        {'code': u.codigo_carpeta, 'subject': u.asunto, 'version': version(u, e),
         'state': e.estado if e else None, 'documents': by_code.get(u.codigo_carpeta, [])}
        for u, e in values
    ]}


@router.get('/documents/{ident}')
def document(ident: int, sha256: str, user: Usuario = Depends(authorized),
             db: Session = Depends(obtener_sesion)):
    row = db.get(Archivo, ident)
    if not row or not row.expediente_id:
        raise HTTPException(404)
    if row.sha256 != sha256:
        raise HTTPException(409, 'Versión de documento distinta.')
    root, path = Path(ALMACEN).resolve(), Path(row.ruta).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404)
    with path.open('rb') as f:
        data = f.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise HTTPException(413)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(409, 'Huella de documento distinta.')
    return Response(data, media_type='application/pdf', headers={'Cache-Control': 'no-store'})


@router.post('/create')
async def create(
    operation_id: UUID = Form(...), device_id: UUID = Form(...),
    code: str = Form(...), base_version: str = Form(...), sha256: str = Form(...),
    pdf: UploadFile = File(...), user: Usuario = Depends(authorized),
    db: Session = Depends(obtener_sesion),
):
    if not re.fullmatch(r'AC-CP-[0-9]{5}', code) or any(
        not re.fullmatch(r'[a-f0-9]{64}', value) for value in [base_version, sha256]
    ):
        raise HTTPException(422, 'Identificador o huella inválida.')
    data = await pdf.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise HTTPException(413)
    if not data.startswith(b'%PDF-') or hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(422, 'El PDF y su SHA-256 no coinciden.')
    await pdf.seek(0)
    # Cross-worker serialization also covers reusing a UUID with another folder.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {'key': 'offline-create-v1'})
    params = {'operation': str(operation_id), 'device': str(device_id),
              'owner': user.correo, 'code': code, 'version': base_version, 'sha': sha256}
    prior = db.execute(text("""
        SELECT device_id::text AS device, owner_email AS owner, codigo_carpeta AS code,
               base_version AS version, pdf_sha256 AS sha, expediente_id AS expedition
        FROM offline_sync_operation WHERE operation_id=:operation
    """), params).mappings().first()
    if prior:
        if any(prior[k] != params[k] for k in ['device', 'owner', 'code', 'version', 'sha']):
            raise HTTPException(409, 'El identificador ya pertenece a otra operación.')
        return {'id': prior['expedition'], 'code': code, 'sha256': sha256, 'replayed': True}
    unit = db.query(UnidadInventario).filter_by(codigo_carpeta=code).with_for_update().first()
    if unit is None:
        raise HTTPException(404, 'Carpeta fuera del inventario.')
    if db.query(Expediente.id).filter_by(codigo_carpeta=code).first() or db.query(Archivo.id).filter_by(codigo_carpeta=code).first():
        raise HTTPException(409, 'La carpeta ya tiene datos en el servidor.')
    if version(unit, None) != base_version:
        raise HTTPException(409, 'El inventario cambió. Revise el conflicto.')
    if db.execute(text('SELECT 1 FROM offline_sync_operation WHERE pdf_sha256=:sha'), params).first():
        raise HTTPException(409, 'El PDF ya fue sincronizado.')
    pdf.filename = code + '.pdf'
    def register(expedition, received_sha):
        if received_sha != sha256:
            raise HTTPException(422, 'El archivo cambió durante la recepción.')
        db.execute(text("""
            INSERT INTO offline_sync_operation VALUES
            (:operation, :device, :owner, :code, :version, :sha, :expedition)
        """), {**params, 'expedition': expedition.id})
        params['expedition'] = expedition.id

    await cargar_documento(pdf, db, user, sync_commit=register)
    return {'id': params['expedition'], 'code': code, 'sha256': sha256, 'replayed': False}


def expedition(db, code, lock=False):
    unit = db.query(UnidadInventario).filter_by(codigo_carpeta=code)
    exp = db.query(Expediente).filter_by(codigo_carpeta=code)
    if lock:
        unit, exp = unit.with_for_update(), exp.with_for_update()
    unit, exp = unit.first(), exp.first()
    if not unit or not exp:
        raise HTTPException(404, 'Expediente fuera del inventario autorizado.')
    return unit, exp


def sheet_data(exp):
    return {
        'nombre_expediente': exp.nombre_expediente or '',
        'archivo_origen': exp.archivo_origen or '',
        'fecha_diligenciamiento': exp.fecha_diligenciamiento.isoformat() if exp.fecha_diligenciamiento else '',
        'periodo_manual': exp.periodo.numero_romano if exp.periodo_fijado_a_mano and exp.periodo else None,
        'tramites': [TramiteEntrada(**{
            **{key: getattr(t, key) if getattr(t, key) is not None else ''
               for key in ('no_item', 'tipo_documental', 'folio_desde', 'folio_hasta', 'no_radicado',
                           'sistema_informacion', 'expediente_sgdea', 'enlace_acceso', 'observaciones')},
            'fecha': t.fecha_texto,
        }).model_dump() for t in sorted(exp.tramites, key=lambda t: t.no_item)],
    }


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sheet_version(unit, exp, sheet):
    return fingerprint([version(unit, exp), sheet])


def derivative(row, kind):
    path = getattr(row, {'matriz': 'ruta_matriz', 'consulta': 'ruta_consulta'}[kind])
    if not path:
        return None
    path = Path(path).resolve()
    if Path(ALMACEN).resolve() not in path.parents or not path.is_file():
        return None
    try:
        with path.open('rb') as file:
            data = file.read(LIMIT+1)
    except OSError:
        return None
    return data if len(data) <= LIMIT and data.startswith(b'%PDF-') else None


@router.get('/work/{code}')
def work(code: str, user: Usuario = Depends(authorized), db: Session = Depends(obtener_sesion)):
    unit, exp = expedition(db, code)
    sheet = sheet_data(exp)
    documents, processing = [], []
    for row in db.query(Archivo).filter_by(expediente_id=exp.id).order_by(Archivo.id):
        available = []
        for kind in ('matriz', 'consulta'):
            data = derivative(row, kind)
            if data is not None:
                available.append(kind)
                documents.append({'id': row.id, 'kind': kind, 'name': f'{row.nombre_original} · {kind}',
                                  'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        processing.append({'name': row.nombre_original, 'pages': row.paginas, 'fragment': row.fragmento,
                           'processed': row.procesado_en.isoformat() if row.procesado_en else None,
                           'error': row.error_proceso, 'derivatives': available})
    return {'code': code, 'state': exp.estado, 'editable': exp.estado in EDITABLE,
            'sheet': sheet, 'version': sheet_version(unit, exp, sheet),
            'processing': processing, 'documents': documents, 'trace': trazabilidad(code, db, user)}


@router.get('/derivatives/{ident}/{kind}')
def download_derivative(ident: int, kind: str, sha256: str, user: Usuario = Depends(authorized),
                        db: Session = Depends(obtener_sesion)):
    row = db.get(Archivo, ident)
    if not row or not row.expediente_id or kind not in ('matriz', 'consulta'):
        raise HTTPException(404)
    expedition(db, row.codigo_carpeta)
    data = derivative(row, kind)
    if data is None:
        raise HTTPException(404)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(409, 'La copia derivada cambió.')
    return Response(data, media_type='application/pdf', headers={'Cache-Control': 'no-store'})


class SheetChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_id: UUID
    device_id: UUID
    base_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    nombre_expediente: str = Field(max_length=500)
    archivo_origen: str = Field(max_length=255)
    fecha_diligenciamiento: str = Field(max_length=32)
    periodo_manual: str | None = Field(max_length=16)
    tramites: list[TramiteEntrada] = Field(min_length=1, max_length=1000)


@router.post('/work/{code}/sheet')
def push_sheet(code: str, change: SheetChange, user: Usuario = Depends(authorized),
               db: Session = Depends(obtener_sesion)):
    values = change.model_dump(mode='json')
    binding = fingerprint([user.correo, code, values])
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))'),
               {'id': str(change.operation_id)})
    unit, exp = expedition(db, code, lock=True)
    prior = db.execute(text('SELECT fingerprint, estado FROM offline_sheet_receipt WHERE operation_id=:id'),
                       {'id': str(change.operation_id)}).first()
    if prior:
        if prior.fingerprint != binding:
            raise HTTPException(409, 'El identificador pertenece a otra operación.')
        return {'operation_id': str(change.operation_id), 'code': code, 'estado': prior.estado, 'replayed': True}
    if exp.estado not in EDITABLE or sheet_version(unit, exp, sheet_data(exp)) != change.base_version:
        raise HTTPException(409, 'La hoja o el expediente cambió. El borrador requiere revisión.')
    hoja = HojaDeControl(codigo_carpeta=code, modo='avance', forzar=False,
                        version=exp.actualizado_en.isoformat() if exp.actualizado_en else None,
                        **{key: value for key, value in values.items()
                           if key not in ('operation_id', 'device_id', 'base_version')})

    def register():
        db.execute(text('INSERT INTO offline_sheet_receipt VALUES (:id,:fingerprint,:estado)'),
                   {'id': str(change.operation_id), 'fingerprint': binding, 'estado': exp.estado})

    result = guardar_hoja(hoja, db, user, sync_commit=register)
    return {'operation_id': str(change.operation_id), 'code': code, 'estado': result['estado'], 'replayed': False}
