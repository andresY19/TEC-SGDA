"""Adaptador de fallos exclusivamente del worker temporal de certificación 10D.

No cambia módulos del producto en disco. Las conversiones y la tarea son reales;
se intercepta sólo el commit de casos sintéticos etiquetados para probar fallos.
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import socket
import uuid

ROOT = Path('/cert')
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-pdfa10d-')
assert os.environ['LEVANTAR_AL_CARGAR'] == 'no'


def audit(kind, **values):
    directory = ROOT/'audit'; directory.mkdir(exist_ok=True)
    with (directory/f'{kind}-{uuid.uuid4().hex}.json').open('x', encoding='utf-8') as f:
        json.dump({'kind':kind, 'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), **values}, f)
        f.flush(); os.fsync(f.fileno())


# Explicitly disallow Python TCP connections outside the two certification peers.
allowed = {(socket.gethostbyname('pg'),5432), (socket.gethostbyname('redis'),6379)}
original_connect = socket.socket.connect


def restricted_connect(self, address):
    if isinstance(address, tuple) and (address[0],address[1]) not in allowed:
        audit('network_denied', host=address[0], port=address[1])
        raise RuntimeError('External connection forbidden in certification worker')
    return original_connect(self, address)


socket.socket.connect = restricted_connect

from celery import current_task, signals
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from geology.nucleo.bd import motor
from geology.nucleo.cola import celery_app
from geology.modelos import Archivo
from geology.dominio import pdfa_controlado as p
import geology.trabajos as jobs


@signals.task_received.connect(weak=False)
def received(sender=None, request=None, **kw):
    audit('received', task_id=request.id, task_name=request.name)


@signals.task_prerun.connect(weak=False)
def prerun(task_id=None, task=None, **kw):
    audit('prerun', task_id=task_id, task_name=task.name)


@signals.task_postrun.connect(weak=False)
def postrun(task_id=None, task=None, state=None, **kw):
    audit('postrun', task_id=task_id, task_name=task.name, state=state)


class CertificationSession(Session):
    def commit(self):
        rows = [x for x in self.dirty if isinstance(x, Archivo)]
        for row in rows:
            for ruta in (row.ruta_matriz, row.ruta_consulta):
                pdf = Path(ruta)
                events = [x for x in pdf.parent.rglob('evento-*.json')
                          if json.loads(x.read_text()).get('estado') == 'validado_publicado'
                          and json.loads(x.read_text()).get('ruta') == ruta]
                assert len(events) == 1
                assert p.verificar_diario(events[0])['verificado']
            # A different real SQL connection must still see the old references.
            with motor.connect() as c:
                persisted = c.execute(text('SELECT ruta_matriz,ruta_consulta FROM archivo_digital WHERE id=:id'), {'id':row.id}).one()
            assert all('/old_' in x for x in persisted)
            audit('validated_before_sql_update', task_id=current_task.request.id,
                  archivo_id=row.id, old_references_still_persisted=True)
            if row.nombre_original == 'SINTETICO_sql_error.pdf':
                # Real PostgreSQL transaction error, subsequently rolled back by product code.
                self.execute(text('SELECT 1/0'))
        super().commit()
        for row in rows:
            if row.nombre_original == 'SINTETICO_commit_uncertain.pdf':
                audit('commit_accepted_ack_lost', task_id=current_task.request.id, archivo_id=row.id)
                raise ConnectionError('SINTETICO: commit aceptado, acuse interrumpido')

    def rollback(self):
        audit('rollback', task_id=current_task.request.id)
        return super().rollback()


jobs.SesionLocal = sessionmaker(bind=motor, class_=CertificationSession,
                               autoflush=False, expire_on_commit=False)
audit('worker_adapter', source_sha256=hashlib.sha256(Path(p.__file__).read_bytes()).hexdigest(),
      product_source_modified=False, faults_limited_to_synthetic_names=True,
      providers_empty=all(not v for k,v in os.environ.items() if 'API_KEY' in k),
      allowed_tcp_peers=sorted([list(x) for x in allowed]))
celery_app.worker_main(['worker','--loglevel=INFO','--concurrency=1', '--without-gossip',
                       '--without-mingle','-Q',os.environ['GEOLOGY_COLA']])
