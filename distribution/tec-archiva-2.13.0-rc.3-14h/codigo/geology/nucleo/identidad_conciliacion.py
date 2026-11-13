"""Read-only local witnesses, combined with host Docker identities by the launcher."""
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
from urllib.parse import urlsplit


def witness(storage_root=None, operation=None, expected_database_addresses=None,
            expected_redis_addresses=None):
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from geology.nucleo.bd import motor

    if not motor.url.host:
        raise ValueError('DATABASE_HOST_NOT_APPROVED')
    resolved = sorted({row[4][0] for row in socket.getaddrinfo(motor.url.host, motor.url.port or 5432)})
    approved = set(expected_database_addresses or [])
    if not approved or not set(resolved).issubset(approved):
        raise ValueError('DATABASE_DNS_IDENTITY_MISMATCH')
    engine = create_engine(motor.url.set(host=resolved[0]), poolclass=NullPool,
                           connect_args={'connect_timeout': 5}, hide_parameters=True)
    with engine.connect() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        database = dict(db.execute(text("""
            SELECT current_database() AS database, current_user AS role,
                   host(inet_server_addr()) AS address, inet_server_port() AS port,
                   (SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid
        """)).mappings().one())
        flags = db.execute(text("""
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
            FROM pg_roles WHERE rolname=current_user
        """)).one()
        if any(flags):
            raise ValueError('ELEVATED_RUNTIME_ROLE')
    engine.dispose()
    if database['address'] not in approved:
        raise ValueError('DATABASE_ADDRESS_MISMATCH')
    roots = {}
    paths = ['/srv/geology/deposito', '/srv/geology/expedidos', '/srv/geology/datos']
    if Path('/cert').is_dir():
        paths.append('/cert')
    for value in paths:
        path = Path(value)
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError('UNSAFE_STORAGE_ROOT')
        roots[value] = {'device': metadata.st_dev, 'inode': metadata.st_ino}
    selected = {key: value for key, value in os.environ.items()
                if key in {'DATABASE_URL', 'CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND',
                           'AUTH_REDIS_URL', 'GEOLOGY_LOCAL_PROJECT', 'GEOLOGY_ENTORNO',
                           'LEVANTAR_AL_CARGAR'} or 'API_KEY' in key or key.startswith('AWS_')}
    environment_hash = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    redis = {}
    for key in ['CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND', 'AUTH_REDIS_URL']:
        url = urlsplit(os.environ[key])
        if not url.hostname or not url.username or not url.password:
            raise ValueError('REDIS_NOT_APPROVED')
        addresses = sorted({row[4][0] for row in socket.getaddrinfo(url.hostname, url.port or 6379)})
        if not addresses or not set(addresses).issubset(set(expected_redis_addresses or [])):
            raise ValueError('REDIS_RESOURCE_MISMATCH')
        redis[key] = {'host': url.hostname, 'port': url.port or 6379,
                      'database': url.path, 'user': url.username, 'addresses': addresses}
    identity = {'hostname': socket.gethostname(), 'uid': os.getuid(), 'gid': os.getgid(),
                'database': database, 'database_resolved_addresses': resolved,
                'storage': roots, 'environment_sha256': environment_hash, 'redis': redis}
    evidence = {}
    if operation is not None:
        root, directory = Path(storage_root).absolute(), Path(operation).absolute()
        if '..' in directory.parts or root not in directory.parents:
            raise ValueError('OPERATION_OUTSIDE_ROOT')
        if any(path.is_symlink() for path in (directory, *directory.parents)):
            raise ValueError('SYMLINK')
        if not directory.is_dir():
            raise ValueError('MISSING_OPERATION')
        count, total, entries = 0, 0, 0
        for path in directory.rglob('*'):
            entries += 1
            if entries > 2048:
                raise ValueError('EVIDENCE_LIMIT')
            if path.name == '.reconciliation.lock' or path.name.startswith('reconciliation-'):
                continue
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError('NON_REGULAR_EVIDENCE')
            count += 1
            total += metadata.st_size
            if count > 1024 or total > 128 * 1024 * 1024:
                raise ValueError('EVIDENCE_LIMIT')
            identity_fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if any(getattr(opened, key) != getattr(metadata, key) for key in identity_fields):
                    raise ValueError('EVIDENCE_CHANGED')
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                finished = os.fstat(stream.fileno())
            current = path.lstat()
            if any(getattr(current, key) != getattr(metadata, key) for key in identity_fields):
                raise ValueError('EVIDENCE_CHANGED')
            if any(getattr(finished, key) != getattr(metadata, key) for key in identity_fields):
                raise ValueError('EVIDENCE_CHANGED')
            evidence[path.relative_to(directory).as_posix()] = {'bytes': metadata.st_size, 'sha256': sha}
    return {'identity': identity, 'evidence': evidence}
