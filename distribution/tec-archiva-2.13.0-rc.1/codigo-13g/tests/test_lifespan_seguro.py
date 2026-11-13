"""Importa la aplicación y ejercita lifespan transitorio sin servidor ni conexiones."""
import json,subprocess,sys,unittest
from pathlib import Path
from test_arranque_estatico import SONDEO

EXTRA=r'''
 import asyncio
 from geology import main
 from geology.nucleo import bd,estructura
 from sqlalchemy.schema import CreateIndex
 from unittest.mock import patch
 result['routes']=[{'path':getattr(r,'path',''),'methods':sorted(getattr(r,'methods',[]) or [])}
     for r in main.aplicacion.routes]
 result['startup_callbacks']=len(main.aplicacion.router.on_startup)
 async def ciclo():
  async with main.aplicacion.router.lifespan_context(main.aplicacion):
   assert main.aplicacion.state.configuracion_validada is True
  assert main.aplicacion.state.configuracion_validada is False
 asyncio.run(ciclo());asyncio.run(ciclo())
 result['lifespan_ok']=True
 with patch.dict(os.environ,{'GEOLOGY_CLAVE':''}):
  try:asyncio.run(ciclo())
  except RuntimeError as exc:result['missing_key_error']=str(exc)
  else:raise AssertionError('No rechazó clave ausente')
 result['state_after_failure']=main.aplicacion.state.configuracion_validada
 with patch.object(main,'registrar_modelos',side_effect=RuntimeError('Registro inválido')):
  try:asyncio.run(ciclo())
  except RuntimeError:result['invalid_registry_blocked']=True
  else:raise AssertionError('No rechazó modelos inválidos')
 result['manual_ddl_blocked']=[]
 for label,env,fn in (
  ('create_all_variable_only',{'GEOLOGY_PERMITIR_DDL':'1','GEOLOGY_ENTORNO':'local'},lambda:bd.crear_tablas()),
  ('alter_variable_only',{'GEOLOGY_PERMITIR_DDL':'1','GEOLOGY_ENTORNO':'local'},lambda:estructura.aplicar()),
  ('create_all_production',{'GEOLOGY_PERMITIR_DDL':'1','GEOLOGY_ENTORNO':'produccion'},lambda:bd.crear_tablas(autorizacion_local=True)),
  ('alter_production',{'GEOLOGY_PERMITIR_DDL':'1','GEOLOGY_ENTORNO':'produccion'},lambda:estructura.aplicar(autorizacion_local=True)),
  ('environment_absent',{'GEOLOGY_PERMITIR_DDL':'1','GEOLOGY_ENTORNO':''},lambda:bd.crear_tablas(autorizacion_local=True))):
  with patch.dict(os.environ,env):
   try:fn()
   except RuntimeError:result['manual_ddl_blocked'].append(label)
   else:raise AssertionError('No rechazó DDL')
 result['schema_proposal']=[]
 for table in Base.metadata.sorted_tables:
  result['schema_proposal'].append({'table':table.name,'primary_key':[c.name for c in table.primary_key],
   'columns':[{'name':c.name,'type':str(c.type),'nullable':c.nullable,
     'python_default':bool(c.default),'server_default':str(c.server_default.arg) if c.server_default else None} for c in table.columns],
   'foreign_keys':[{'column':fk.parent.name,'target':fk.target_fullname,'ondelete':fk.ondelete} for fk in table.foreign_keys],
   'create_table_sql':str(CreateTable(table).compile(dialect=dialect())),
   'indexes':[{'name':i.name,'unique':i.unique,'sql':str(CreateIndex(i).compile(dialect=dialect()))} for i in sorted(table.indexes,key=lambda i:i.name)]})
 result['guard_calls']=sum(g.call_count for g in guards)
'''

SCRIPT=SONDEO.replace("if p.name=='main.py':continue","if False:continue")
SCRIPT=SCRIPT.replace('print(json.dumps(result))',EXTRA+'\nprint(json.dumps(result))')


class LifespanSeguro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=subprocess.run([sys.executable,'-B','-c',SCRIPT],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=50)
        if p.returncode:raise AssertionError(p.stderr)
        cls.r=json.loads(p.stdout)
    def test_01_import_completo(self):self.assertEqual(self.r['errors'],[]);self.assertTrue(self.r['main_imported'])
    def test_02_lifespan_repetible_sin_servicio(self):self.assertTrue(self.r['lifespan_ok'])
    def test_03_clave_ausente_bloquea(self):self.assertIn('Sesiones no configuradas',self.r['missing_key_error'])
    def test_04_error_no_deja_estado_listo(self):self.assertFalse(self.r['state_after_failure'])
    def test_05_modelos_invalidos_bloquean(self):self.assertTrue(self.r['invalid_registry_blocked'])
    def test_06_sin_callback_ddl_heredado(self):self.assertEqual(self.r['startup_callbacks'],0)
    def test_07_variable_no_autoriza_ddl(self):self.assertTrue({'create_all_variable_only','alter_variable_only'}<=set(self.r['manual_ddl_blocked']))
    def test_08_produccion_no_admite_ddl(self):self.assertTrue({'create_all_production','alter_production'}<=set(self.r['manual_ddl_blocked']))
    def test_09_entorno_ausente_bloquea_ddl(self):self.assertIn('environment_absent',self.r['manual_ddl_blocked'])
    def test_10_cero_efectos(self):self.assertEqual(self.r['guard_calls'],0)
    def test_11_registro_rutas(self):
        rutas={r['path'] for r in self.r['routes']}
        self.assertTrue({'/estado','/cuentas/ingresar','/cuentas/yo'}<=rutas)
        self.assertGreater(len(rutas),100)
    def test_12_metadata(self):self.assertEqual(len(self.r['schema_proposal']),27)


if __name__=='__main__':unittest.main()
