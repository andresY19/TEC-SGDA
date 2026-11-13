"""Certificación 10B aislada, con logs persistentes y límites de recursos.

No monta .env, depósito, volúmenes ni redes originales. Usa la imagen existente
por digest, sin descarga ni construcción. No inicia servicios GEOLOGY.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'sha256:a77f24483c87e509b9c48d34fe1a76f115ac92688c4156b7ab1d8e049f1e7a10'


def main():
    if shutil.disk_usage(Path.home()).free < 2 * 1024**3:
        raise RuntimeError('Capacidad insuficiente para las pruebas sintéticas.')
    base = Path.home()/'GEOLOGY_PDFA_Tests'/('phase10b-'+uuid.uuid4().hex[:12])
    base.mkdir(parents=True, exist_ok=False)
    for name in ('geology', 'tests'):
        shutil.copytree(ROOT/name, base/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('results', 'tmp'):
        (base/name).mkdir()
    legacy = Path(json.loads((ROOT/'phase10a-certification-location.json').read_text())['directory'])
    hashes = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
              for name in ('geology', 'tests') for p in (base/name).rglob('*.py')}
    (base/'results/source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    command = ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none',
        '--cpus', '2', '--memory', '3g', '--memory-swap', '3g', '--pids-limit', '256',
        '-v', str(base)+':/work:ro', '-v', str(base/'results')+':/work/results',
        '-v', str(base/'tmp')+':/work/tmp', '-v', str(legacy)+':/legacy:ro', '-w', '/work',
        '-e', 'PYTHONPATH=/work', '-e', 'TMPDIR=/work/tmp',
        '-e', 'DATABASE_URL=postgresql+psycopg2://synthetic:synthetic@db.invalid/synthetic',
        '-e', 'GEOLOGY_ENTORNO=test', '-e', 'GEOLOGY_LOCAL_PROJECT=geology-pdfa10b-isolated',
        '-e', 'GEOLOGY_COLA=geology-pdfa10b-isolated-tasks',
        '-e', 'CELERY_BROKER_URL=redis://redis.invalid:6379/14',
        '-e', 'CELERY_RESULT_BACKEND=redis://redis.invalid:6379/15',
        '--entrypoint', 'python', IMAGE, '-B']
    negative = '''import sys,importlib.util,unittest,json
sys.path.insert(0,'/work/tests')
import test_diario_verapdf as t
spec=importlib.util.spec_from_file_location('old_pdfa','/legacy/geology/dominio/pdfa_controlado.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);t.p=old
r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
t.DiarioVeraPDF('test_regresion_ruta_no_se_sustituye_por_elemento_xml')]))
assert len(r.failures)==1 and not r.errors, 'El control no reprodujo el defecto'
print(json.dumps({'expected_old_defect_reproduced':True,'expected_assertion_failures':1}))
'''
    suites = [('negative_control_expected_failure', ['-c', negative]),
              ('unit', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']),
              ('integration', ['tests/integration_pdfa_controlado.py'])]
    result = {'directory': str(base), 'legacy_readonly_directory': str(legacy), 'image': IMAGE,
              'network': 'none', 'active_mounts': [], 'cpu_limit': 2, 'memory_limit_gib': 3,
              'suites': {}}
    (ROOT/'phase10b-certification-location.json').write_text(json.dumps(result, indent=2))
    for kind, tail in suites:
        with (base/f'results/{kind}-stdout.txt').open('x', encoding='utf-8') as stdout, \
             (base/f'results/{kind}-stderr.txt').open('x', encoding='utf-8') as stderr:
            r = subprocess.run(command+tail, stdout=stdout, stderr=stderr, timeout=900)
        log = (base/f'results/{kind}-stderr.txt').read_text(encoding='utf-8')
        match = re.search(r'Ran (\d+) tests?', log)
        result['suites'][kind] = {'returncode': r.returncode,
            'tests': int(match[1]) if match else None, 'pass': r.returncode == 0,
            'excluded_from_passed_failed_totals': kind == 'negative_control_expected_failure'}
        print(kind, r.returncode, log[-2400:], flush=True)
        (ROOT/'phase10b-certification-results.json').write_text(json.dumps(result, indent=2))
        if r.returncode:
            raise SystemExit(r.returncode)
    print(str(base), flush=True)


if __name__ == '__main__':
    main()
