from pathlib import Path
import json,subprocess,sys
B=Path(__file__).resolve().parent/'campaign-full'
sys.path.insert(0,str(B/'scripts'))
import certify_autonomous_13c as c
c.STATE.update(json.loads((B/'phase13c-environment.json').read_text()))
assert c.STATE['project'].startswith('geology-auto11e-a11y13c-full-')
runner=c.cid('runner')
info=json.loads(subprocess.check_output(['docker','inspect',runner]))[0]
assert info['Config']['Labels']['com.docker.compose.project']==c.STATE['project']
source=r"""
import os
from geology.nucleo.bd import SesionLocal,registrar_modelos
from geology.modelos import UnidadInventario, Expediente, Tramite, UsuarioBD
from geology.dominio.estados import Estado
from geology.dominio.publicacion import es_publicable
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11e-a11y13c-full-')
assert os.environ['LEVANTAR_AL_CARGAR']=='no'
registrar_modelos()
with SesionLocal.begin() as session:
    entity=session.query(UsuarioBD).filter_by(correo='entidad13c@example.invalid').one()
    entity.ve_hojas_control=False
    entity.ve_isadg=False
    entity.ve_fuid=False
    entity.ve_imagenes=False
    for i in range(14):
        code='AC-CP-'+str(99900+i)
        assert not session.query(Expediente).filter_by(codigo_carpeta=code).first()
        session.add(UnidadInventario(codigo_carpeta=code,caja_origen='SYN13C',periodo='I' if i<12 else 'II',folios=1,asunto='SINTETICO 13C'))
        record=Expediente(codigo_carpeta=code,caja_origen='SYN13C',estado=Estado.HOJA_REVISADA.value,
          publicado_consulta=i<13,nombre_expediente='SINTETICO 13C '+str(i),volumen_folios=1)
        record.tramites.append(Tramite(no_item=1,tipo_documental='Oficio sintetico',folio_desde=1,folio_hasta=1))
        session.add(record)
        session.flush()
        assert es_publicable(session,record)==(i<13),code
print('14 synthetic records, 13 published and 1 reserved')
"""
r=subprocess.run(['docker','exec','-i',runner,'python','-B','-'],input=source,capture_output=True,text=True,encoding='utf-8')
assert r.returncode==0,r.stderr[-700:]
print(r.stdout.strip())
