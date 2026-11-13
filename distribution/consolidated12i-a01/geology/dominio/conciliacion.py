"""11D: passive reconciliation. Never repair, regenerate, delete or redeliver.

Only the isolated operator invokes this service; no HTTP/Celery auto-retry route.
Existing upload inventory locks and PDF/A row locks are reused. Decisions are
immutable sidecars; the source journal is never rewritten. No Redis dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from sqlalchemy import text


class EvidenceUnavailable(RuntimeError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def safe_path(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    if '..' in path.parts or '..' in root.parts:
        raise EvidenceUnavailable('UNSAFE_PATH')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise EvidenceUnavailable('SYMLINK')
    if path != root and root not in path.parents:
        raise EvidenceUnavailable('OUTSIDE_STORAGE')
    return path


def read_file(root, path, limit=None):
    path = safe_path(root, path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        a = os.fstat(fd)
        if not stat.S_ISREG(a.st_mode) or (limit is not None and a.st_size > limit):
            raise EvidenceUnavailable('INVALID_FILE')
        chunks, h = [], hashlib.sha256()
        while True:
            b = os.read(fd, 1024 * 1024)
            if not b:
                break
            h.update(b)
            if limit is not None:
                chunks.append(b)
                if sum(map(len, chunks)) > limit:
                    raise EvidenceUnavailable('OVERSIZE_JOURNAL')
        z = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if identity(a) != identity(z) or identity(a) != identity(current):
            raise EvidenceUnavailable('FILE_CHANGED')
        return h.hexdigest(), b''.join(chunks), a.st_size
    finally:
        os.close(fd)


def load_json(root, path):
    sha, raw, _ = read_file(root, path, 2 * 1024 * 1024)
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise EvidenceUnavailable('DUPLICATE_JSON_KEY')
            result[k] = v
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise EvidenceUnavailable('INVALID_JOURNAL')
    return value, sha


def _verify(root, evidence, observed):
    if not isinstance(evidence, dict) or not isinstance(evidence.get('ruta'), str):
        raise EvidenceUnavailable('INCOMPLETE_FILE_EVIDENCE')
    if not re.fullmatch('[a-f0-9]{64}', str(evidence.get('sha256', ''))):
        raise EvidenceUnavailable('INCOMPLETE_HASH')
    sha, _, size = read_file(root, evidence['ruta'])
    if sha != evidence['sha256']:
        raise EvidenceUnavailable('HASH_MISMATCH')
    if evidence.get('tamano_bytes') is not None and evidence['tamano_bytes'] != size:
        raise EvidenceUnavailable('SIZE_MISMATCH')
    observed[str(safe_path(root, evidence['ruta']))] = sha


def _upload(db, root, directory, journal, observed):
    from geology.modelos import Archivo, UnidadInventario
    j, jsha = load_json(root, journal)
    if j.get('version') != 1 or j.get('operacion') != directory.name:
        raise EvidenceUnavailable('OPERATION_BINDING')
    folder = j.get('codigo_carpeta')
    if not isinstance(folder, str) or not folder:
        raise EvidenceUnavailable('MISSING_RESOURCE')
    lock = db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == folder).with_for_update(nowait=True).first()
    if lock is None:
        raise EvidenceUnavailable('MISSING_RESOURCE')
    # Lock acquired on the same resource as the real producer; refresh journal.
    j2, jsha2 = load_json(root, journal)
    if jsha != jsha2:
        raise EvidenceUnavailable('JOURNAL_CHANGED')
    rows = db.query(Archivo).filter(Archivo.codigo_carpeta == folder).with_for_update(nowait=True).all()
    current = {r.id: r for r in rows}
    expected = j.get('registros')
    if not isinstance(expected, list) or not expected:
        return 'NEEDS_REVIEW', 'NO_AUTHORITATIVE_SQL_RECEIPT', jsha, {}
    if not isinstance(j.get('original'), dict):
        raise EvidenceUnavailable('INCOMPLETE_ORIGINAL')
    safe_path(directory, j['original'].get('ruta', ''))
    _verify(root, j.get('original'), observed)
    seen = set()
    for entry in expected:
        if not isinstance(entry, dict) or type(entry.get('id')) is not int or entry['id'] in seen:
            raise EvidenceUnavailable('INVALID_RECORD_SET')
        seen.add(entry['id'])
        safe_path(directory, entry.get('ruta', ''))
        _verify(root, entry, observed)
        row = current.get(entry['id'])
        if row is None:
            return 'NEEDS_REVIEW', 'SQL_ABSENT_NOT_PROOF_OF_ROLLBACK', jsha, {}
        for key in ('codigo_carpeta', 'expediente_id', 'ruta', 'sha256', 'tamano_bytes', 'fragmento'):
            if key not in entry or getattr(row, key) != entry[key]:
                return 'NEEDS_REVIEW', 'SQL_REFERENCE_CONFLICT', jsha, {}
    if any(r.id not in seen and str(r.ruta).startswith(str(directory) + os.sep) for r in rows):
        raise EvidenceUnavailable('UNEXPECTED_OPERATION_REFERENCE')
    for old in j.get('anteriores', []):
        _verify(root, old, observed)
        if old.get('id') in current:
            return 'NEEDS_REVIEW', 'REPLACEMENT_NOT_CONFIRMED', jsha, {}
    sql = {str(i): {'ruta': current[i].ruta, 'sha256': current[i].sha256,
                    'expediente_id': current[i].expediente_id} for i in sorted(seen)}
    return 'COMMITTED', 'EXACT_SQL_AND_DOCUMENT_MATCH', jsha, sql


def _pdfa(db, root, directory, observed):
    from geology.modelos import Archivo
    from geology.dominio.pdfa_controlado import verificar_diario
    events = []
    for path in sorted(directory.glob('evento-*.json')):
        value, sha = load_json(root, path)
        events.append((path, value, sha))
    # Event payload uses 'estado'; do not guess on unsupported journal formats.
    pending = [e for e in events if e[1].get('estado') == 'commit_pendiente_conciliar_si_interrumpido']
    started = [e for e in events if e[1].get('estado') == 'iniciado']
    if len(pending) != 1 or len(started) != 1:
        raise EvidenceUnavailable('INCOMPLETE_PDFA_JOURNAL')
    p, initial = pending[0][1], started[0][1]
    if type(p.get('archivo_id')) is not int or p['archivo_id'] != initial.get('archivo_id'):
        raise EvidenceUnavailable('PDFA_RESOURCE_BINDING')
    row = db.get(Archivo, p['archivo_id'], with_for_update={'nowait': True})
    if row is None:
        raise EvidenceUnavailable('MISSING_SQL_REFERENCE')
    if row.sha256 != initial.get('origen_sha256'):
        raise EvidenceUnavailable('PDFA_ORIGINAL_HASH_CONFLICT')
    _verify(root, {'ruta': row.ruta, 'sha256': initial.get('origen_sha256')}, observed)
    sql = {'id': row.id, 'ruta': row.ruta, 'sha256': row.sha256}
    for kind in ('matriz', 'consulta'):
        evidence = p.get(kind)
        if not isinstance(evidence, dict):
            raise EvidenceUnavailable('INCOMPLETE_PDFA_EVIDENCE')
        safe_path(directory, evidence.get('ruta', ''))
        _verify(root, evidence, observed)
        if getattr(row, 'ruta_' + kind) != evidence['ruta']:
            raise EvidenceUnavailable('PDFA_SQL_REFERENCE_CONFLICT')
        validations = []
        for path in directory.glob('.pdfa-*/evento-*.json'):
            val, _ = load_json(root, path)
            if val.get('estado') == 'validado_publicado' and val.get('ruta') == evidence['ruta']:
                validations.append(path)
        if len(validations) != 1:
            raise EvidenceUnavailable('MISSING_VALIDATION_RECEIPT')
        validation, validation_sha = load_json(root, validations[0])
        observed[str(validations[0])] = validation_sha
        _verify(root, {'ruta': str(validations[0].parent / 'verapdf.xml'),
                       'sha256': validation.get('informe_sha256')}, observed)
        verificar_diario(validations[0])
        if evidence.get('ruta_texto'):
            _verify(root, {'ruta': evidence['ruta_texto'], 'sha256': evidence.get('texto_sha256')}, observed)
        sql[kind] = evidence['ruta']
    if row.ruta_texto != p['consulta'].get('ruta_texto'):
        raise EvidenceUnavailable('PDFA_TEXT_REFERENCE_CONFLICT')
    for path, _, sha in events:
        observed[str(path)] = sha
    return 'COMMITTED', 'EXACT_PDFA_SQL_AND_VALIDATION_MATCH', digest(canonical([(str(x[0]), x[2]) for x in events])), sql


def reconcile(directory, storage_root, sessions):
    """Return immutable observation. No business DML and no task publication.

    An unavailable DB cannot be recorded as a rollback. Legacy missing receipts
    require review. RECONCILED means a verified observation, never re-delivery.
    """
    import fcntl  # Linux runtime; fail closed on unsupported lock platforms.
    root = safe_path(storage_root, storage_root)
    directory = safe_path(root, directory)
    if not directory.is_dir():
        raise EvidenceUnavailable('OPERATION_DIRECTORY_MISSING')
    ident = str(directory.relative_to(root))
    lockpath = directory / '.reconciliation.lock'
    fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EvidenceUnavailable('UNSAFE_LOCK')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise EvidenceUnavailable('CONCURRENT_RECONCILIATION') from None
    db = None
    observed = {}
    source_hash = None
    sql = {}
    try:
        journal = directory / 'operacion.json'
        try:
            db = sessions()
            # No waiting for a producer while retaining filesystem locks.
            db.execute(text("SET LOCAL lock_timeout='2s'"))
            if journal.exists():
                _, source_hash = load_json(root, journal)
                outcome, reason, source_hash, sql = _upload(db, root, directory, journal, observed)
            else:
                outcome, reason, source_hash, sql = _pdfa(db, root, directory, observed)
            if journal.exists() and load_json(root, journal)[1] != source_hash:
                raise EvidenceUnavailable('JOURNAL_CHANGED')
            for path, expected in observed.items():
                if read_file(root, path)[0] != expected:
                    raise EvidenceUnavailable('FILE_CHANGED')
        except Exception as exc:
            outcome = 'NEEDS_REVIEW'
            reason = str(exc) if isinstance(exc, EvidenceUnavailable) else 'EVIDENCE_UNAVAILABLE_' + type(exc).__name__
            sql = {}
        result = {'contract': 1, 'operation': ident,
                  'state': 'RECONCILED' if outcome == 'COMMITTED' else 'NEEDS_REVIEW',
                  'outcome': outcome, 'reason': reason, 'source_sha256': source_hash,
                  'documents': observed, 'sql': sql, 'automatic_delivery': False,
                  'automatic_deletion': False}
        payload = canonical(result)
        receipt = directory / ('reconciliation-' + digest(payload) + '.json')
        try:
            with receipt.open('xb') as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
            parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except FileExistsError:
            if read_file(root, receipt, 2 * 1024 * 1024)[1] != payload:
                raise EvidenceUnavailable('RECEIPT_CONFLICT') from None
        return result
    finally:
        try:
            if db is not None:
                try:
                    db.rollback()  # Read/lock-only TX: never commits business state.
                finally:
                    db.close()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
