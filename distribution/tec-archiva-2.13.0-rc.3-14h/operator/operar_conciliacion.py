"""Host-only reconciliation authority and launcher. Never mount Docker in the app."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import time


class Denied(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise Denied('DUPLICATE_JSON_KEY')
            value[key] = item
        return value
    raw = Path(path).read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise Denied('OVERSIZE_DOCUMENT')
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise Denied('INVALID_DOCUMENT')
    return value


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())


def initialize_ledger(directory):
    """Create only the new host audit ledger during trusted provisioning."""
    target = Path(directory) / 'consumed.sqlite'
    if target.exists():
        raise Denied('LEDGER_ALREADY_EXISTS')
    db = sqlite3.connect(target)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('''CREATE TABLE consumed (
            authorization_id TEXT PRIMARY KEY, authorization_sha256 TEXT NOT NULL,
            policy_sha256 TEXT NOT NULL, resource_sha256 TEXT NOT NULL,
            challenge_sha256 TEXT NOT NULL, operation TEXT NOT NULL,
            consumed_at INTEGER NOT NULL, result_sha256 TEXT, finished_at INTEGER)''')
        db.commit()
    finally:
        db.close()


def consume(policy, ticket, envelope, challenge, resources):
    ledger = Path(policy['host_ledger_path'])
    if not ledger.is_dir() or ledger.is_symlink():
        raise Denied('AUDIT_LEDGER_UNAVAILABLE')
    uri = (ledger/'consumed.sqlite').as_uri() + '?mode=rw'
    db = sqlite3.connect(uri, uri=True, timeout=10)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO consumed VALUES (?,?,?,?,?,?,?,NULL,NULL)',
                   (ticket['id'], digest(envelope), digest(policy), digest(resources),
                    digest(challenge), ticket['operation'], int(time.time())))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise Denied('AUTHORIZATION_ALREADY_CONSUMED') from None
    finally:
        db.close()
    return ledger/ticket['id']


def finish(policy, ticket, result):
    uri = (Path(policy['host_ledger_path'])/'consumed.sqlite').as_uri() + '?mode=rw'
    db = sqlite3.connect(uri, uri=True, timeout=10)
    try:
        db.execute('PRAGMA synchronous=FULL')
        changed = db.execute('UPDATE consumed SET result_sha256=?,finished_at=? '
                             'WHERE authorization_id=? AND finished_at IS NULL',
                             (digest(result), int(time.time()), ticket['id']))
        if changed.rowcount != 1:
            raise Denied('AUDIT_STATE_CONFLICT')
        db.commit()
    finally:
        db.close()


def docker(*args, input=None):
    result = subprocess.run(['docker', *args], input=input, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=45)
    if result.returncode:
        raise Denied('DOCKER_INSPECTION_OR_EXECUTION_FAILED')
    return result.stdout


def crypto(node, request):
    helper = Path(__file__).with_name('crypto_host.mjs')
    result = subprocess.run([str(node), str(helper)], input=json.dumps(request),
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise Denied('CRYPTOGRAPHIC_OPERATION_FAILED')
    return json.loads(result.stdout)


def sign(policy, payload, key):
    result = crypto(policy['node_binary'], {'action': 'sign', 'private_key': Path(key).read_text(),
                    'message': base64.b64encode(canonical(payload)).decode()})
    return {'payload': payload, 'signature': result['signature']}


def verify(policy, envelope):
    if set(envelope) != {'payload', 'signature'}:
        raise Denied('INVALID_AUTHORIZATION')
    result = crypto(policy['node_binary'], {'action': 'verify',
                    'public_key': policy['authority_public_key'],
                    'message': base64.b64encode(canonical(envelope['payload'])).decode(),
                    'signature': envelope['signature']})
    if not result['valid']:
        raise Denied('INVALID_AUTHORIZATION_SIGNATURE')
    return envelope['payload']


def probe(container, addresses, redis_addresses, root=None, operation=None):
    source = 'import json\nfrom pathlib import Path\nfrom geology.nucleo.identidad_conciliacion import witness\n'
    source += 'print(json.dumps(witness('+repr(root)+','+repr(operation)+','+repr(addresses)+','+repr(redis_addresses)+')))\n'
    return json.loads(docker('exec', '-i', container, 'python', '-B', '-', input=source))


def snapshot(service_ids, protected, purpose):
    """Check Docker identities before probing a database or documentary path."""
    containers = json.loads(docker('inspect', *service_ids.values()))
    by_id = {value['Id']: value for value in containers}
    if set(by_id) != set(service_ids.values()):
        raise Denied('FULL_CONTAINER_IDS_REQUIRED')
    result = {'services': {}, 'volumes': {}, 'networks': {}}
    for role, ident in service_ids.items():
        item = by_id[ident]
        if purpose == 'rehearsal' and ident in protected['container_ids']:
            raise Denied('PROTECTED_CONTAINER')
        if not item['State']['Running']:
            raise Denied('TARGET_NOT_RUNNING')
        host = item['HostConfig']
        ports = host['PortBindings'] or {}
        if ports and (purpose == 'rehearsal' or any(
                binding['HostIp'] not in {'127.0.0.1', '::1'}
                for bindings in ports.values() for binding in bindings)):
            raise Denied('PUBLISHED_PORTS_NOT_ALLOWED')
        mounts = []
        for mount in item['Mounts']:
            if mount['Type'] == 'volume':
                name = mount['Name']
                if purpose == 'rehearsal' and name in protected['volume_names']:
                    raise Denied('PROTECTED_VOLUME')
                raw = json.loads(docker('volume', 'inspect', name))[0]
                if purpose == 'rehearsal' and (raw['Driver'] != 'local' or raw.get('Options')):
                    raise Denied('EXTERNAL_OR_WRAPPED_VOLUME')
                result['volumes'][name] = {key: raw[key] for key in
                    ['Name', 'Driver', 'Mountpoint', 'CreatedAt', 'Labels', 'Options', 'Scope']}
            else:
                allowed = {'/run/secrets/reconciliation-policy.json', '/cert-redis.conf', '/cert-users.acl'}
                if purpose == 'operation':
                    allowed.update({'/srv/geology/deposito', '/srv/geology/expedidos',
                                    '/srv/geology/datos', '/usr/local/etc/redis/redis.conf',
                                    '/usr/local/etc/redis/users.acl'})
                if mount['Type'] != 'bind' or mount['Destination'] not in allowed:
                    raise Denied('UNAPPROVED_BIND_MOUNT')
            mounts.append({key: mount.get(key) for key in ['Type', 'Name', 'Source', 'Destination', 'RW']})
        networks = {}
        for name, network in item['NetworkSettings']['Networks'].items():
            netid = network['NetworkID']
            if purpose == 'rehearsal' and netid in protected['network_ids']:
                raise Denied('PROTECTED_NETWORK')
            raw = json.loads(docker('network', 'inspect', netid))[0]
            if not raw['Internal'] and (purpose == 'rehearsal' or role in {'pg', 'redis'}):
                raise Denied('NON_PRIVATE_NETWORK')
            result['networks'][netid] = {'id': raw['Id'], 'created': raw['Created'],
                                       'driver': raw['Driver'], 'internal': raw['Internal'],
                                       'ipam': raw['IPAM']}
            networks[netid] = network['IPAddress']
        config = item['Config']
        result['services'][role] = {
            'id': ident, 'image': item['Image'], 'hostname': config['Hostname'],
            'config_sha256': digest(config), 'mounts': sorted(mounts, key=lambda m: m['Destination']),
            'networks': networks, 'user': config['User'], 'read_only_root': host['ReadonlyRootfs'],
            'cap_drop': host['CapDrop'], 'security_opt': host['SecurityOpt']}
    for role in ['web', 'worker']:
        target = result['services'][role]
        if (target['user'] != '10001:10001' or not target['read_only_root']
                or 'ALL' not in target['cap_drop']
                or not any('no-new-privileges' in value for value in target['security_opt'] or [])):
            raise Denied('UNSAFE_RUNTIME')
        addresses = set(result['services']['pg']['networks'].values())
        redis_addresses = sorted(result['services']['redis']['networks'].values())
        witness = probe(target['id'], sorted(addresses), redis_addresses)['identity']
        if (witness['uid'], witness['gid']) != (10001, 10001):
            raise Denied('UNSAFE_EFFECTIVE_USER')
        if witness['database']['address'] not in addresses or not set(witness['database_resolved_addresses']).issubset(addresses):
            raise Denied('DATABASE_RESOURCE_MISMATCH')
        target['witness'] = witness
    control = docker('exec', '--user', 'postgres', service_ids['pg'], 'env', 'LC_ALL=C',
                     'pg_controldata', '/var/lib/postgresql/data')
    match = re.search(r'Database system identifier:\s*(\d+)', control)
    if not match:
        raise Denied('POSTGRES_CLUSTER_ID_UNAVAILABLE')
    result['postgres_system_identifier'] = match[1]
    return result


def validated_policy(path):
    policy = read_json(path)
    if policy.get('version') != 1 or policy.get('purpose') not in {'rehearsal', 'operation'}:
        raise Denied('INVALID_POLICY')
    if not 0 < policy['max_seconds'] <= 300:
        raise Denied('INVALID_AUTHORIZATION_LIFETIME')
    node = Path(policy['node_binary'])
    if hashlib.sha256(node.read_bytes()).hexdigest() != policy['node_sha256']:
        raise Denied('VERIFIER_BINARY_CHANGED')
    return policy


def current_resources(policy):
    ids = {role: resource['id'] for role, resource in policy['resources']['services'].items()}
    current = snapshot(ids, policy['protected_resources'], policy['purpose'])
    if current != policy['resources']:
        raise Denied('CURRENT_RESOURCES_DO_NOT_MATCH_POLICY')
    return current


def issue(policy_path, key_path, target, operation, root, destination):
    policy = validated_policy(policy_path)
    resources = current_resources(policy)
    if target not in policy['target_services'] or root not in policy['storage_roots']:
        raise Denied('OUTSIDE_ALLOWED_SCOPE')
    addresses = list(resources['services']['pg']['networks'].values())
    redis_addresses = list(resources['services']['redis']['networks'].values())
    evidence = probe(resources['services'][target]['id'], addresses, redis_addresses, root, operation)['evidence']
    if not evidence:
        raise Denied('REQUIRED_EVIDENCE_MISSING')
    now = int(time.time())
    payload = {'version': 1, 'id': secrets.token_hex(16), 'purpose': policy['purpose'],
               'action': 'reconcile', 'max_runs': 1, 'policy_sha256': digest(policy),
               'resource_sha256': digest(resources), 'target_service': target,
               'target_container_id': resources['services'][target]['id'],
               'operation': operation, 'storage_root': root, 'evidence_sha256': digest(evidence),
               'issued_at': now, 'expires_at': now + policy['max_seconds']}
    envelope = sign(policy, payload, key_path)
    verify(policy, envelope)
    write_new(destination, envelope)
    return payload['id']


def execute(policy_path, runner_key, authorization_path, target=None, operation=None, root=None):
    policy = validated_policy(policy_path)
    envelope = read_json(authorization_path)
    ticket = verify(policy, envelope)
    now = int(time.time())
    if (ticket.get('purpose') != policy['purpose'] or ticket.get('action') != 'reconcile'
            or ticket.get('max_runs') != 1 or ticket.get('policy_sha256') != digest(policy)
            or type(ticket.get('issued_at')) is not int or type(ticket.get('expires_at')) is not int
            or not ticket['issued_at'] <= now < ticket['expires_at']
            or not 0 < ticket['expires_at']-ticket['issued_at'] <= policy['max_seconds']):
        raise Denied('EXPIRED_OR_INCORRECT_SCOPE')
    if not re.fullmatch('[a-f0-9]{32}', str(ticket.get('id', ''))):
        raise Denied('INVALID_AUTHORIZATION_ID')
    target = target or ticket['target_service']
    operation = operation or ticket['operation']
    root = root or ticket['storage_root']
    if (target != ticket['target_service'] or operation != ticket['operation']
            or root != ticket['storage_root'] or target not in policy['target_services']
            or root not in policy['storage_roots']):
        raise Denied('REQUEST_OUTSIDE_AUTHORIZATION')
    resources = current_resources(policy)
    if ticket['resource_sha256'] != digest(resources):
        raise Denied('RESOURCE_IDENTITY_MISMATCH')
    ident = resources['services'][target]['id']
    if ident != ticket['target_container_id']:
        raise Denied('TARGET_IDENTITY_MISMATCH')
    addresses = list(resources['services']['pg']['networks'].values())
    redis_addresses = list(resources['services']['redis']['networks'].values())
    observed = probe(ident, addresses, redis_addresses, root, operation)
    if not observed['evidence'] or digest(observed['evidence']) != ticket['evidence_sha256']:
        raise Denied('OPERATION_EVIDENCE_CHANGED')
    process = subprocess.Popen(['docker', 'exec', '-i', ident, 'python', '-B',
                                '/opt/geology-distribution/reconcile_documents.py',
                                '--operation', operation, '--storage-root', root, '--authorization-stdin'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8')
    audit = None
    try:
        # Read one bounded challenge, not an application result or credential.
        challenge_line = process.stdout.readline(32769)
        challenge = json.loads(challenge_line)['challenge']
        if (len(challenge_line) > 32768 or challenge['policy_sha256'] != digest(policy)
                or challenge['hostname'] != resources['services'][target]['hostname']
                or not re.fullmatch('[a-f0-9]{64}', challenge['nonce'])):
            raise Denied('INVALID_PROCESS_CHALLENGE')
        if current_resources(policy) != resources:
            raise Denied('RESOURCE_CHANGED_DURING_LAUNCH')
        audit = consume(policy, ticket, envelope, challenge, resources)
        audit.mkdir()
        # An interrupted run remains consumed and auditable. Never reset it.
        write_new(audit/'started.json', {'authorization_id': ticket['id'], 'authorization_sha256': digest(envelope),
                  'policy_sha256': digest(policy), 'resource_sha256': digest(resources),
                  'challenge_sha256': digest(challenge), 'operation': operation, 'state': 'CONSUMED',
                  'issued_at': int(time.time())})
        issued = int(time.time())
        proof = {'version': 1, 'ticket_sha256': digest(envelope), 'challenge': challenge,
                 'resource_sha256': digest(resources), 'operation_evidence_sha256': ticket['evidence_sha256'],
                 'consumed': True, 'issued_at': issued, 'expires_at': issued + 30}
        packet = {'authorization': envelope, 'execution': sign(policy, proof, runner_key)}
        output, error = process.communicate(json.dumps(packet)+'\n', timeout=60)
        result = json.loads(output.strip())
        if process.returncode not in (0, 2, 77):
            raise Denied('EXECUTION_UNCERTAIN')
        write_new(audit/'finished.json', {'authorization_id': ticket['id'], 'exit_code': process.returncode,
                  'result': result, 'result_sha256': digest(result), 'finished_at': int(time.time())})
        finish(policy, ticket, result)
        return process.returncode, result
    finally:
        if process.poll() is None:
            # Closing the pipe denies a process waiting for proof. If already
            # executing, retain CONSUMED and require evidence-based recovery.
            try:
                process.communicate('', timeout=5)
            except (subprocess.TimeoutExpired, ValueError):
                process.kill()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    issuer = sub.add_parser('issue')
    issuer.add_argument('--policy', required=True)
    issuer.add_argument('--authority-key', required=True)
    issuer.add_argument('--target', choices=['web', 'worker'], required=True)
    issuer.add_argument('--operation', required=True)
    issuer.add_argument('--storage-root', choices=['/cert', '/srv/geology/deposito'], required=True)
    issuer.add_argument('--output', required=True)
    runner = sub.add_parser('run')
    runner.add_argument('--policy', required=True)
    runner.add_argument('--runner-key', required=True)
    runner.add_argument('--authorization', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'issue':
            ident = issue(args.policy, args.authority_key, args.target, args.operation, args.storage_root, args.output)
            print(json.dumps({'authorization_id': ident, 'state': 'ISSUED'}))
            return 0
        code, result = execute(args.policy, args.runner_key, args.authorization)
        print(json.dumps(result))
        return code
    except Exception as error:
        reason = str(error) if isinstance(error, Denied) else 'CONTROLLED_EXECUTION_UNAVAILABLE'
        print(json.dumps({'state': 'DENIED', 'reason': reason}))
        return 77


if __name__ == '__main__':
    raise SystemExit(main())

