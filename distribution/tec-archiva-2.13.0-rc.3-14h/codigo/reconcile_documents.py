"""Controlled, single-operation reconciliation. No implicit project approval."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation', required=True)
    parser.add_argument('--storage-root', choices=['/cert', '/srv/geology/deposito'], required=True)
    parser.add_argument('--local-project', help='Display context only; never grants authorization.')
    parser.add_argument('--authorization-stdin', action='store_true')
    args = parser.parse_args()
    operation, root = Path(args.operation), Path(args.storage_root)
    if not args.authorization_stdin:
        print(json.dumps({'state': 'DENIED', 'reason': 'SPECIFIC_AUTHORIZATION_REQUIRED'}))
        return 77
    try:
        from geology.nucleo.autorizacion_conciliacion import authorize, digest
        ticket, policy = authorize(sys.stdin, sys.stdout, operation, root)
        from geology.nucleo.identidad_conciliacion import witness
        approved_addresses = list(policy['resources']['services']['pg']['networks'].values())
        redis_addresses = list(policy['resources']['services']['redis']['networks'].values())
        observed = witness(root, operation, approved_addresses, redis_addresses)
        target = policy['resources']['services'][ticket['target_service']]
        if observed['identity'] != target['witness'] or digest(observed['evidence']) != ticket['evidence_sha256']:
            raise ValueError('CURRENT_EVIDENCE_OR_IDENTITY_MISMATCH')
    except Exception:
        print(json.dumps({'state': 'DENIED', 'reason': 'AUTHORIZATION_OR_IDENTITY_INVALID'}))
        return 77
    try:
        from geology.dominio.conciliacion import reconcile
        from geology.nucleo.bd import SesionLocal, motor
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool
        engine = create_engine(motor.url.set(host=observed['identity']['database']['address']),
                               poolclass=NullPool, connect_args={'connect_timeout': 5}, hide_parameters=True)
        session_options = {key: value for key, value in SesionLocal.kw.items() if key != 'bind'}
        try:
            result = reconcile(operation, root, sessionmaker(bind=engine, **session_options))
        finally:
            engine.dispose()
    except Exception:
        print(json.dumps({'state': 'NEEDS_REVIEW', 'reason': 'RECONCILIATION_UNAVAILABLE',
                          'human_review_required': True, 'authorization_id': ticket['id']}))
        return 2
    print(json.dumps({'state': result['state'], 'outcome': result['outcome'],
                      'reason': result['reason'], 'human_review_required': result['state'] == 'NEEDS_REVIEW',
                      'authorization_id': ticket['id']}))
    return 0 if result['state'] == 'RECONCILED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
