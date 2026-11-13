from pathlib import Path
import secrets,json,subprocess,sys
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'));import certify_autonomous_12f as c
c.STATE.update(json.loads((B/'phase12f-environment.json').read_text()));assert c.STATE['project'].startswith('geology-auto11e-ux12f-')
pw=secrets.token_urlsafe(32)
source=r'''
import os,hashlib
from pathlib import Path
import pikepdf
from geology.nucleo.bd import SesionLocal,registrar_modelos
from geology.modelos import UsuarioBD,cifrar_clave,Expediente,Archivo,Trazabilidad
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11e-ux12f-')
assert all(not v for k,v in os.environ.items() if 'API_KEY' in k)
registrar_modelos()
with SesionLocal.begin() as s:
 for role in ['administradora','equipo','lider','consulta','entidad']:
  assert not s.query(UsuarioBD).filter_by(correo=role+'12f@example.invalid').first()
  s.add(UsuarioBD(nombre='SINTETICO UX12F '+role,correo=role+'12f@example.invalid',rol=role,funcion='Ambas',activo=True,debe_cambiar_clave=False,clave_hash=cifrar_clave(PASSWORD),intentos_fallidos=0,ve_imagenes=False))
 exp=Expediente(codigo_carpeta='AC-CP-99881',titulo='SINTETICO UX12F <script> no ejecutar',estado='En cola');s.add(exp);s.flush()
 base=Path('/srv/geology/deposito/sintetico12f');base.mkdir(exist_ok=False)
 for i in [1,2]:
  p=base/('parte-'+str(i)+'.pdf')
  with pikepdf.Pdf.new() as pdf:
   pdf.add_blank_page(page_size=(200,200))
   with p.open('xb') as f:pdf.save(f)
  s.add(Archivo(expediente_id=exp.id,codigo_carpeta=exp.codigo_carpeta,fragmento=i,nombre_original=p.name,ruta=str(p),tamano_bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),paginas=1,subido_por='SINTETICO UX12F'))
 s.add(Trazabilidad(expediente_id=exp.id,estado_nuevo='En cola',accion='Preparación sintética UX12F',usuario='SINTETICO UX12F'))
print('Five synthetic users, one queued expediente, two synthetic PDF parts prepared')
'''
r=subprocess.run(['docker','exec','-i',c.cid('runner'),'python','-B','-'],input='PASSWORD='+repr(pw)+'\n'+source,text=True,encoding='utf-8',capture_output=True);assert r.returncode==0,r.stderr[-1000:]
(B/'control/ui-private.json').write_text(json.dumps({'password':pw,'port':c.STATE['port']}),encoding='utf-8');print(r.stdout)
