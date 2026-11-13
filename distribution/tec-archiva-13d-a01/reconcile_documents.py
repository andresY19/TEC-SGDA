"""Explicit operator entry point; not an automatic repair or delivery worker."""
import argparse
import json
import os
from pathlib import Path

from geology.dominio.conciliacion import reconcile, EvidenceUnavailable
from geology.nucleo.bd import SesionLocal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', required=True)
    parser.add_argument('--storage-root', choices=['/cert','/srv/geology/deposito'], required=True)
    args = parser.parse_args()
    if not os.environ.get('GEOLOGY_LOCAL_PROJECT','').startswith('geology-auto11e-'):
        raise SystemExit('BLOCKED: isolated 11E certification only')
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
