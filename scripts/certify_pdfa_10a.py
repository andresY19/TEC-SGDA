"""Certificación reproducible aislada. No monta .env, depósito ni volúmenes activos.

Crea únicamente copias sintéticas nuevas en C:. Los resultados se conservan.
No publica tareas y no conecta a PostgreSQL/Redis. Usa la imagen local existente.
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
        raise RuntimeError('Capacidad insuficiente para la certificación sintética.')
    base = Path.home()/'GEOLOGY_PDFA_Tests'/('phase10a-certified-'+uuid.uuid4().hex[:12])
    base.mkdir(parents=True, exist_ok=False)
    for name in ('geology', 'tests'):
        shutil.copytree(ROOT/name, base/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('results', 'tmp'):
        (base/name).mkdir()
    hashes = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
              for name in ('geology', 'tests') for p in (base/name).rglob('*.py')}
    (base/'results/source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    command = ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none',
        '-v', str(base)+':/work:ro', '-v', str(base/'results')+':/work/results',
        '-v', str(base/'tmp')+':/work/tmp', '-w', '/work',
        '-e', 'PYTHONPATH=/work', '-e', 'TMPDIR=/work/tmp',
        '-e', 'DATABASE_URL=postgresql+psycopg2://synthetic:synthetic@db.invalid/synthetic',
        '-e', 'GEOLOGY_ENTORNO=test', '-e', 'GEOLOGY_LOCAL_PROJECT=geology-pdfa10a-isolated',
        '-e', 'GEOLOGY_COLA=geology-pdfa10a-isolated-tasks',
        '-e', 'CELERY_BROKER_URL=redis://redis.invalid:6379/14',
        '-e', 'CELERY_RESULT_BACKEND=redis://redis.invalid:6379/15',
        '--entrypoint', 'python', IMAGE, '-B']
    result = {'directory': str(base), 'image': IMAGE, 'network': 'none',
              'active_mounts': [], 'suites': {}}
    (ROOT/'phase10a-certification-location.json').write_text(json.dumps(result, indent=2))
    for kind, tail in [('unit', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']),
                       ('integration', ['tests/integration_pdfa_controlado.py'])]:
        r = subprocess.run(command+tail, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        for stream in ('stdout', 'stderr'):
            (base/f'results/{kind}-{stream}.txt').write_text(getattr(r, stream), encoding='utf-8')
        match = re.search(r'Ran (\d+) tests', r.stderr)
        result['suites'][kind] = {'returncode': r.returncode,
            'tests': int(match[1]) if match else None, 'pass': r.returncode == 0}
        print(kind, r.returncode, r.stderr[-2400:], flush=True)
        (ROOT/'phase10a-certification-results.json').write_text(json.dumps(result, indent=2))
        if r.returncode:
            raise SystemExit(r.returncode)
    print(str(base), flush=True)


if __name__ == '__main__':
    main()
