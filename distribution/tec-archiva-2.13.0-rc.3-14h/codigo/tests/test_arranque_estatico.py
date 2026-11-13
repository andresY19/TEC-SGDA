"""Carga real de módulos en proceso separado; main solo se analiza, nunca se inicia."""
import json,subprocess,sys,unittest
from pathlib import Path

SONDEO=r'''
import ast,contextlib,importlib,json,os,secrets,sys
from pathlib import Path
from unittest.mock import patch
os.environ.clear()
os.environ.update(DATABASE_URL='postgresql+psycopg2://synthetic:synthetic@db.invalid:5432/synthetic',
 CELERY_BROKER_URL='redis://redis.invalid:6379/14',CELERY_RESULT_BACKEND='redis://redis.invalid:6379/15',
 GEOLOGY_LOCAL_PROJECT='geology-import-audit',GEOLOGY_COLA='geology-import-audit-tasks',
 GEOLOGY_CLAVE=secrets.token_urlsafe(32))
with contextlib.ExitStack() as stack:
 guards=[stack.enter_context(patch(name,side_effect=AssertionError('Efecto prohibido'))) for name in
  ('socket.socket.connect','socket.create_connection','psycopg2.connect','sqlalchemy.engine.Engine.connect',
   'sqlalchemy.engine.Engine.begin','sqlalchemy.sql.schema.MetaData.create_all',
   'celery.app.task.Task.apply','celery.app.task.Task.apply_async','kombu.Connection.connect')]
 dotenv=stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
 files=sorted(Path('geology').rglob('*.py'));loaded=[];errors=[]
 for p in files:
  ast.parse(p.read_text(encoding='utf-8-sig'))
  if p.name=='main.py':continue
  parts=list(p.with_suffix('').parts)
  if parts[-1]=='__init__':parts.pop()
  name='.'.join(parts)
  try:importlib.import_module(name);loaded.append(name)
  except Exception as exc:errors.append({'module':name,'error':type(exc).__name__,'detail':str(exc)[:180]})
 from geology.nucleo.bd import Base,registrar_modelos
 registrar_modelos()
 from sqlalchemy.schema import CreateTable
 from sqlalchemy.dialects.postgresql import dialect
 compiled=[str(CreateTable(t).compile(dialect=dialect())) for t in Base.metadata.sorted_tables]
 result={'loaded':loaded,'errors':errors,'tables':len(compiled),'guard_calls':sum(g.call_count for g in guards),
         'main_imported':'geology.main' in sys.modules,'dotenv_suppressed':dotenv.call_count}
print(json.dumps(result))
'''


class ArranqueEstatico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=subprocess.run([sys.executable,'-B','-c',SONDEO],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=50)
        if p.returncode:raise AssertionError(p.stderr)
        cls.r=json.loads(p.stdout)
    def test_imports_locales_reales(self):self.assertEqual(self.r['errors'],[])
    def test_orm_completo(self):self.assertEqual(self.r['tables'],27)
    def test_sin_arranque_conexiones_ni_tareas(self):
        self.assertFalse(self.r['main_imported']);self.assertEqual(self.r['guard_calls'],0)


if __name__=='__main__':unittest.main()
