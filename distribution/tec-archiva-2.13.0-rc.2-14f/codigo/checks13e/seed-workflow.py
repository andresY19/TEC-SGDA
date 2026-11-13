from pathlib import Path
import json,subprocess,sys
B=Path(__file__).resolve().parent
E=B/'campaign-full'
state=json.loads((E/'phase13e-environment.json').read_text())
assert state['project'].startswith('geology-auto11e-a11y13e-full-')
ids=subprocess.check_output(['docker','ps','-q','--filter','label=com.docker.compose.project='+state['project'],'--filter','label=com.docker.compose.service=runner'],text=True).split()
assert len(ids)==1
source=r"""
import os,hashlib,json,sys,time
import pikepdf
from pathlib import Path
from geology.nucleo.bd import SesionLocal,registrar_modelos
from geology.modelos import UnidadInventario,Expediente,Archivo,Trazabilidad
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11e-a11y13e-full-')
assert os.environ['LEVANTAR_AL_CARGAR']=='no'
registrar_modelos()
with SesionLocal.begin() as s:
 if sys.argv[1]=='prepare':
  target=Path('/tmp/AC-CP-99996.pdf')
  with pikepdf.Pdf.new() as pdf:
   pdf.add_blank_page(page_size=(205,210))
   pdf.docinfo['/Title']='Cargue sintético TEC-ARCHIVA 13E 99996'
   with target.open('xb') as f:pdf.save(f)
  s.add(UnidadInventario(codigo_carpeta='AC-CP-99996',caja_origen='CARGUE13E',periodo='I',folios=1,asunto='Cargue sintético 13E'))
  s.add(Expediente(codigo_carpeta='AC-CP-99997',estado='Descripción por validar',titulo='Revisión sintética 13E',describio='SINTETICO UX13E equipo'))
 else:
  a=s.query(Archivo).filter_by(codigo_carpeta='AC-CP-99996').one()
  p=Path(a.ruta)
  x=s.query(Expediente).filter_by(codigo_carpeta='AC-CP-99996').one()
  r=s.query(Expediente).filter_by(codigo_carpeta='AC-CP-99997').one()
  digest=hashlib.sha256(p.read_bytes()).hexdigest()
  assert digest==a.sha256==sys.argv[2]
  assert x.estado=='En cola' and r.estado=='Descripción por validar'
  traces=s.query(Trazabilidad).filter_by(expediente_id=x.id).count()
  assert traces
  derivados=[Path(ruta) for ruta in (a.ruta_matriz,a.ruta_consulta) if ruta]
  assert all(p.is_file() for p in derivados)
  print(json.dumps({'sha256':digest,'bytes':p.stat().st_size,'archivos':1,'estado':x.estado,'trazas':traces,'revision':r.estado,'derivados':[{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in derivados]}))
"""
if sys.argv[1]=='prepare':
 subprocess.run(['docker','exec','-i',ids[0],'python','-B','-','prepare'],input=source,text=True,encoding='utf-8',check=True)
if sys.argv[1] in ('prepare','export'):
 with (B/'AC-CP-99996.pdf').open('xb') as out:
  subprocess.run(['docker','exec',ids[0],'cat','/tmp/AC-CP-99996.pdf'],stdout=out,check=True)
else:
 import hashlib
 out=subprocess.run(['docker','exec','-i',ids[0],'python','-B','-','check',hashlib.sha256((B/'AC-CP-99996.pdf').read_bytes()).hexdigest()],input=source,text=True,encoding='utf-8',capture_output=True)
 assert out.returncode==0,out.stderr
 (B/'results/integridad13e.json').write_text(out.stdout)

