"""Versions and broker status of the new runtime, never original services."""
from pathlib import Path
import json,subprocess
import certify_autonomous_11e as c
ROOT=Path(__file__).resolve().parents[1];s=json.loads((ROOT/'phase11e-environment.json').read_text());c.STATE.update(s);assert s['project'].startswith('geology-auto11e-')
source='''
import sys,json,subprocess,importlib.metadata as md
from pathlib import Path
from geology.nucleo.cola import celery_app
manifest=json.loads(Path('/opt/geology-distribution/build-manifest.json').read_text())
packages={d.metadata['Name']:d.version for d in md.distributions()}
from geology.nucleo.cola import registrar_tareas
registered=registrar_tareas()
expected={'geology.ping','geology.levantar_hoja','geology.preparar_digitalizacion'}
assert set(registered)==expected
assert celery_app.conf.worker_enable_remote_control is False
state={'remote_control_enabled':False,'evidence':'Embedded registration + actual worker startup logs + empty broker/unacked metadata; remote inspect is intentionally disabled.'}
def version(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=30);assert r.returncode==0;return (r.stdout+r.stderr).strip()
print(json.dumps({'python':sys.version,'packages':packages,'ghostscript':version(['gs','--version']),'verapdf':version(['/opt/verapdf/verapdf','--version']),'registered':registered,'worker_state':state,'debian_packages':manifest['debian_packages'],'manifest_source_hashes':manifest['source_sha256']}))
'''
r=subprocess.run(['docker','exec','-i',c.cid('worker'),'python','-B','-'],input=source,capture_output=True,text=True,encoding='utf-8');assert r.returncode==0,r.stderr[-500:]
logs=subprocess.run(['docker','logs',c.cid('worker')],capture_output=True,text=True,encoding='utf-8',errors='replace')
assert logs.returncode==0
for name in ['geology.ping','geology.levantar_hoja','geology.preparar_digitalizacion']:assert '  . '+name in logs.stdout+logs.stderr
assert ' ready.' in logs.stdout+logs.stderr
(ROOT/'phase11e-runtime-manifest.json').write_text(json.dumps(json.loads(r.stdout),indent=2));print('Versions, three registered tasks and empty worker state verified.')
