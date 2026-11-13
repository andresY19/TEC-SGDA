"""Explicit operator entry point; not an automatic repair or delivery worker."""
import argparse
import json
import os
import re
from pathlib import Path

from geology.dominio.conciliacion import reconcile
from geology.nucleo.bd import SesionLocal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', required=True)
    parser.add_argument('--storage-root', choices=['/cert','/srv/geology/deposito'], required=True)
    parser.add_argument('--local-project', help='Explicitly confirm the isolated local project.')
    args = parser.parse_args()
    project = os.environ.get('GEOLOGY_LOCAL_PROJECT', '')
    if args.local_project is None:
        if not project.startswith('geology-auto11e-'):
            raise SystemExit('BLOCKED: confirm the isolated environment with --local-project')
    elif (
        args.local_project != project
        or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', project)
        or project == 'geology-local-20261106-57a99a'
        or os.environ.get('GEOLOGY_ENTORNO', '').lower() not in ('local', 'test', 'testing', 'pruebas')
    ):
        raise SystemExit('BLOCKED: isolated local project confirmation is invalid')
    if os.environ.get('LEVANTAR_AL_CARGAR') != 'no':
        raise SystemExit('BLOCKED: AI must remain disabled')
    try:
        r = reconcile(Path(args.operation),Path(args.storage_root),SesionLocal)
    except Exception:
        print(json.dumps({'state':'NEEDS_REVIEW','reason':'RECONCILIATION_UNAVAILABLE','human_review_required':True}))
        return 2
    print(json.dumps({'state':r['state'],'outcome':r['outcome'],'reason':r['reason'],
                      'human_review_required':r['state']=='NEEDS_REVIEW'}))
    return 0 if r['state']=='RECONCILED' else 2


if __name__ == '__main__':raise SystemExit(main())
