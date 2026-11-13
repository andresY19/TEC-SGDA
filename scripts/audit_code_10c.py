"""Auditoría de fuentes sin conversiones, DDL, DML, tareas ni contenedores nuevos.

El sondeo de imports es un proceso de diagnóstico independiente, no introspección
de la memoria de Uvicorn/Celery. Se conserva esa distinción en los resultados.
"""
from operational_9f_tools import *
import tarfile
import subprocess

FILES = ('geology/main.py', 'geology/nucleo/bd.py', 'geology/nucleo/cola.py',
         'geology/trabajos/__init__.py', 'geology/dominio/recepcion_tecnica.py',
         'geology/dominio/pdfa_controlado.py', 'geology/dominio/validador_pdfa.py')

PROBE = r'''
import sys,os,json,hashlib,inspect,dis,socket
from pathlib import Path
from unittest.mock import patch
guards=[patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')),
 patch('socket.create_connection',side_effect=AssertionError('Network forbidden')),
 patch('psycopg2.connect',side_effect=AssertionError('DB forbidden')),
 patch('sqlalchemy.engine.Engine.connect',side_effect=AssertionError('Connection forbidden')),
 patch('sqlalchemy.sql.schema.MetaData.create_all',side_effect=AssertionError('DDL forbidden')),
 patch('celery.app.task.Task.apply_async',side_effect=AssertionError('Publication forbidden')),
 patch('celery.app.task.Task.apply',side_effect=AssertionError('Task execution forbidden'))]
spies=[g.start() for g in guards]
try:
 import geology.main as main
 after_main={n:n in sys.modules for n in ['geology.main','geology.trabajos','geology.dominio.recepcion_tecnica','geology.dominio.pdfa_controlado']}
 import geology.trabajos as jobs
 from geology.nucleo.cola import celery_app,registrar_tareas
 registered=registrar_tareas()
 lazy_before='geology.dominio.pdfa_controlado' in sys.modules
 import geology.dominio.pdfa_controlado as p
 import geology.dominio.recepcion_tecnica as r
 functions={'preparar_digitalizacion':str(inspect.signature(jobs.preparar_digitalizacion.run)),
  'matriz_de_preservacion':str(inspect.signature(r.matriz_de_preservacion)),
  'validar':str(inspect.signature(p.validar)),
  'verificar_diario':str(inspect.signature(p.verificar_diario))}
 # The 10B fix is checked in compiled Python instructions, not only a filename.
 stores=[i.argval for i in dis.get_instructions(p.validar) if i.opname=='STORE_FAST']
 assert 'informe' not in stores and 'validacion' in stores
 assert p.perfil_efectivo(None)=='2b' and p.perfil_efectivo('1b')=='1b'
 assert 'perfil_solicitado' in inspect.signature(jobs.preparar_digitalizacion.run).parameters
 for s in spies:s.assert_not_called()
 files={name:{'file':'/srv/geology/'+name,'sha256':hashlib.sha256(Path('/srv/geology',name).read_bytes()).hexdigest()} for name in FILES}
 out={'probe_type':'fresh guarded diagnostic process, not live-process memory inspection',
  'pid1_command':Path('/proc/1/cmdline').read_bytes().replace(b'\0',b' ').decode(),
  'modules_after_main_import':after_main,'pdfa_loaded_before_explicit_probe_import':lazy_before,
  'effective_version':main.aplicacion.version,'module_files':{m.__name__:m.__file__ for m in [main,jobs,p,r]},
  'task_code_filename':jobs.preparar_digitalizacion.run.__code__.co_filename,
  'files':files,'signatures':functions,'journal_fix_bytecode_verified':True,
  'registered_tasks':list(registered),'broker':celery_app.conf.broker_url,
  'queue':celery_app.conf.task_default_queue,'remote_control_enabled':celery_app.conf.worker_enable_remote_control,
  'configured_pdfa_default':os.environ.get('PDFA_PERFIL'),'legacy_processing_default':p.perfil_efectivo(None),
  'network_calls':0,'ddl_calls':0,'task_publications':0,'task_executions':0}
 print(json.dumps(out))
finally:
 for g in reversed(guards):g.stop()
'''


def main():
    evidence = json.loads((ROOT/'phase10c-recovery-evidence.json').read_text())
    out = {'services':{}, 'image_source':{}}
    for name in ('servidor','procesador'):
        cid = evidence['services'][name]['id']
        p = command(['docker','exec','-i',cid,'python','-B','-'],
                    input='FILES='+repr(FILES)+'\n'+PROBE)
        if p.returncode:
            raise RuntimeError('Guarded code probe failed: '+name)
        result = json.loads(p.stdout)
        result['all_host_file_hashes_equal'] = all(v['sha256']==hashlib.sha256((ROOT/k).read_bytes()).hexdigest()
                                                   for k,v in result['files'].items())
        if not result['all_host_file_hashes_equal']:
            raise RuntimeError('Mounted source mismatch')
        result['container_started_at'] = evidence['services'][name]['started_at']
        result['source_last_modified_utc'] = {n:datetime.datetime.fromtimestamp((ROOT/n).stat().st_mtime,datetime.timezone.utc).isoformat() for n in FILES}
        out['services'][name]=result
    (ROOT/'phase10c-code-probes.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    # Export streams the underlying container rootfs, excluding mounted volume/bind
    # contents. No archive is created. Read only source files from the image path.
    cid = evidence['services']['procesador']['id']
    image = object_inspect('image',evidence['services']['procesador']['image'])
    found = {}
    proc = subprocess.Popen(['docker','export',cid],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
        for member in archive:
            path=member.name.removeprefix('./').lstrip('/')
            if path.startswith('srv/geology/'):
                relative=path[len('srv/geology/'):]
                if relative in FILES and member.isfile():
                    data=archive.extractfile(member).read()
                    found[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    stderr=proc.stderr.read();code=proc.wait()
    if code:
        raise RuntimeError('Read-only rootfs export failed')
    for name in FILES:
        found.setdefault(name,{'present':False})
        found[name]['same_as_host']=found[name].get('sha256')==hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    out['image_source']={'method':'streamed docker export of existing worker underlying rootfs; mounted contents excluded; no files extracted',
        'image_id':image['Id'],'created':image['Created'],'files':found,
        'limitation':'Underlying rootfs includes its container writable layer; read-only bind-mounted application source cannot overwrite the underlying image copy.'}
    out['interpretation']={'rebuild_required_for_this_bound_local_environment':False,
        'self_contained_image_contains_10b_code':False,
        'live_process_memory_introspection_performed':False,
        'evidence_of_task_module_startup_load':'Celery include geology.trabajos, registered tasks in actual startup log, fresh container process started after frozen source update; host-mounted source hashes verified.',
        'pdfa_controlado_loading':'Lazy import inside task. Presence/fix/importability certified by guarded probe, not claimed as already imported into idle live worker memory.',
        'user_profile_selector_added':False,'operational_pdfa_task_executed':False}
    (ROOT/'phase10c-code-probes.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps({'runtime_version':out['services']['servidor']['effective_version'],
        'mounted_source_matches':True,'journal_fix_verified':True,'image_files':found,
        'rebuild_required_for_local_bind':False},indent=2),flush=True)


if __name__=='__main__':
    main()
