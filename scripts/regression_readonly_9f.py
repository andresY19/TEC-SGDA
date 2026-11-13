"""22 selected regressions. No integration fixture, publication or restart test.

15 guarded subprocess import/lifespan tests + 6 read-only PG/Redis tests run
inside the existing server, with read-only SQL connections. One host HTTP test.
Test modules are loaded from strings; no active documents or code are written.
"""
from pathlib import Path
import json,subprocess,sys,os
ROOT=Path(__file__).resolve().parents[1]
PROJECT='geology-local-20261106-57a99a'

def main():
    sources={name:(ROOT/'tests'/name).read_text(encoding='utf-8-sig') for name in
        ('test_arranque_estatico.py','test_lifespan_seguro.py','integration_postgres_local.py')}
    selected=['test_01_conexion','test_02_tablas_y_columnas','test_03_claves_foraneas',
        'test_04_indices_y_pk','test_09_transporte_redis_sin_worker','test_10_tipos_nulabilidad_unique_y_checks']
    code='''import sys,types,unittest,json
sources=SOURCES
for filename,source in sources.items():
 name=filename[:-3];module=types.ModuleType(name);module.__file__='/srv/geology/tests/'+filename
 sys.modules[name]=module;exec(compile(source,module.__file__,'exec'),module.__dict__)
suite=unittest.TestSuite()
for name in ('test_arranque_estatico','test_lifespan_seguro'):
 suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[name]))
cls=sys.modules['integration_postgres_local'].PostgreSQLLocal
suite.addTests(cls(name) for name in SELECTED)
result=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}))
sys.exit(not result.wasSuccessful())
'''.replace('SOURCES',repr(sources)).replace('SELECTED',repr(selected))
    p=subprocess.run(['docker','exec','-i','-e','GEOLOGY_INTEGRATION=local-approved',
        '-e','PGOPTIONS=-c default_transaction_read_only=on',PROJECT+'-servidor-1','python','-B','-'],
        input=code,capture_output=True,text=True,encoding='utf-8',errors='replace')
    container={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    host_code="import sys,unittest;sys.path.insert(0,'tests');from integration_http_local import HTTPLocal;r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([HTTPLocal('test_01_http_interfaz_y_rutas')]));sys.exit(not r.wasSuccessful())"
    h=subprocess.run([sys.executable,'-B','-c',host_code],cwd=ROOT,env=dict(os.environ,GEOLOGY_HTTP_INTEGRATION='local-approved'),
        capture_output=True,text=True,encoding='utf-8',errors='replace')
    result={'container':container,'host_http':{'returncode':h.returncode,'stdout':h.stdout,'stderr':h.stderr},
        'policy':'Selected readonly tests only. Guarded synthetic import/lifespan subprocesses block connections, DDL and task application. No setup from auth/document/Celery publication integrations.'}
    (ROOT/'phase9f-regression-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(p.stderr[-2400:]);print(h.stderr[-800:]);print('return codes',p.returncode,h.returncode)
    if p.returncode or h.returncode:sys.exit(1)

if __name__=='__main__':main()
