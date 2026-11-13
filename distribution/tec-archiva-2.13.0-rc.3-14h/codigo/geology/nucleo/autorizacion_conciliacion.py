"""Verify host authorization; the application never receives a Docker socket."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

POLICY = Path('/run/secrets/reconciliation-policy.json')
MAX_DOCUMENT = 2 * 1024 * 1024


class AuthorizationDenied(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorizationDenied('DUPLICATE_KEY')
        result[key] = value
    return result


def decode(raw):
    if len(raw) > MAX_DOCUMENT:
        raise AuthorizationDenied('OVERSIZE_AUTHORIZATION')
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise AuthorizationDenied('INVALID_DOCUMENT')
    return value


def verify_signed(envelope, public_key):
    if set(envelope) != {'payload', 'signature'}:
        raise AuthorizationDenied('INVALID_ENVELOPE')
    key = serialization.load_pem_public_key(public_key.encode())
    if not isinstance(key, Ed25519PublicKey):
        raise AuthorizationDenied('INVALID_KEY_TYPE')
    key.verify(base64.b64decode(envelope['signature'], validate=True), canonical(envelope['payload']))
    return envelope['payload']


def within_window(payload, maximum, now):
    start, end = payload.get('issued_at'), payload.get('expires_at')
    if type(start) is not int or type(end) is not int:
        raise AuthorizationDenied('INVALID_TIME_WINDOW')
    if not start <= now < end or not 0 < end - start <= maximum:
        raise AuthorizationDenied('AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID')


def process_challenge(policy):
    fields = Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()
    return {'protocol': 1, 'nonce': secrets.token_hex(32), 'pid': os.getpid(),
            'start_ticks': fields[19], 'mount_namespace': os.stat('/proc/self/ns/mnt').st_ino,
            'hostname': socket.gethostname(), 'policy_sha256': digest(policy)}


def validate_packet(policy, challenge, packet, operation, storage_root, now=None):
    """Pure validation before database access or receipt creation."""
    now = int(time.time()) if now is None else now
    if policy.get('version') != 1 or policy.get('purpose') not in {'rehearsal', 'operation'}:
        raise AuthorizationDenied('INVALID_POLICY')
    if set(packet) != {'authorization', 'execution'}:
        raise AuthorizationDenied('INVALID_PACKET')
    ticket = verify_signed(packet['authorization'], policy['authority_public_key'])
    proof = verify_signed(packet['execution'], policy['runner_public_key'])
    if ticket.get('version') != 1 or proof.get('version') != 1:
        raise AuthorizationDenied('INVALID_PROTOCOL_VERSION')
    if (not re.fullmatch('[a-f0-9]{32}', str(ticket.get('id', '')))
            or not re.fullmatch('[a-f0-9]{64}', str(ticket.get('evidence_sha256', '')))):
        raise AuthorizationDenied('REQUIRED_EVIDENCE_MISSING')
    within_window(ticket, min(policy['max_seconds'], 300), now)
    within_window(proof, 30, now)
    target = ticket.get('target_service')
    resources = policy['resources']
    if target not in policy['target_services']:
        raise AuthorizationDenied('TARGET_NOT_ALLOWED')
    expected = resources['services'][target]
    protected = policy['protected_resources']
    if policy['purpose'] == 'rehearsal':
        ids = {v['id'] for v in resources['services'].values()}
        if (ids.intersection(protected['container_ids'])
                or set(resources['volumes']).intersection(protected['volume_names'])
                or set(resources['networks']).intersection(protected['network_ids'])):
            raise AuthorizationDenied('REHEARSAL_CANNOT_AUTHORIZE_PROTECTED_RESOURCES')
    if ticket.get('purpose') != policy['purpose'] or ticket.get('action') != 'reconcile':
        raise AuthorizationDenied('AUTHORIZATION_SCOPE')
    if ticket.get('max_runs') != 1:
        raise AuthorizationDenied('SINGLE_USE_REQUIRED')
    if ticket.get('policy_sha256') != digest(policy) or ticket.get('resource_sha256') != digest(resources):
        raise AuthorizationDenied('RESOURCE_IDENTITY_MISMATCH')
    if ticket.get('target_container_id') != expected['id']:
        raise AuthorizationDenied('TARGET_IDENTITY_MISMATCH')
    if ticket.get('operation') != str(operation) or ticket.get('storage_root') != str(storage_root):
        raise AuthorizationDenied('OPERATION_OUTSIDE_SCOPE')
    if storage_root.as_posix() not in policy['storage_roots']:
        raise AuthorizationDenied('STORAGE_OUTSIDE_SCOPE')
    if (proof.get('ticket_sha256') != digest(packet['authorization'])
            or proof.get('challenge') != challenge
            or proof.get('consumed') is not True
            or proof.get('resource_sha256') != digest(resources)
            or proof.get('operation_evidence_sha256') != ticket.get('evidence_sha256')):
        raise AuthorizationDenied('INVALID_EXECUTION_ATTESTATION')
    if challenge['hostname'] != expected['hostname']:
        raise AuthorizationDenied('PROCESS_TARGET_MISMATCH')
    return ticket


def authorize(stream, output, operation, storage_root):
    metadata = POLICY.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or os.access(POLICY, os.W_OK):
        raise AuthorizationDenied('TRUST_POLICY_NOT_PROTECTED')
    policy = decode(POLICY.read_bytes())
    challenge = process_challenge(policy)
    output.write(json.dumps({'challenge': challenge}) + '\n')
    output.flush()
    raw = stream.readline(MAX_DOCUMENT + 1)
    if not raw:
        raise AuthorizationDenied('AUTHORIZATION_REQUIRED')
    ticket = validate_packet(policy, challenge, decode(raw), operation, storage_root)
    if os.environ.get('LEVANTAR_AL_CARGAR') != 'no':
        raise AuthorizationDenied('AUTOMATIC_READING_ENABLED')
    if any(value for key, value in os.environ.items()
           if 'API_KEY' in key or key in {'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'}):
        raise AuthorizationDenied('EXTERNAL_CREDENTIALS_PRESENT')
    return ticket, policy
