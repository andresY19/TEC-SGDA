"""Copy each legacy DPAPI vault into its own consolidated profile."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from workspace import protect


LEGACY = {'piloto': 'TEC-SGDEA', 'preview': 'TEC-SGDEA-Preview',
          'fichas': 'TEC-SGDEA-Fichas', 'trabajo': 'TEC-SGDEA-Trabajo'}
CURRENT_SERVER = 'http://127.0.0.1:18099'


def endpoint(database):
    if database.is_file():
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as db:
            row = db.execute("SELECT payload FROM vault WHERE slot='lease'").fetchone()
        if row:
            return json.loads(protect(row[0], False))['server']
    return CURRENT_SERVER


def copy_vault(source, destination):
    if destination.exists():
        return True
    if not source.is_file():
        return False
    with TemporaryDirectory(dir=destination.parent) as temporary:
        candidate = Path(temporary)/'workspace.sqlite3'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(candidate)) as copy:
                original.backup(copy)
                if copy.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError('SQLite no superó la comprobación de integridad.')
                if not copy.execute('SELECT 1 FROM vault LIMIT 1').fetchone():
                    return False
                if not copy.execute("SELECT 1 FROM vault WHERE slot='lease'").fetchone():
                    raise ValueError('El almacén contiene datos sin identidad offline.')
                for payload, in copy.execute('SELECT payload FROM vault'):
                    json.loads(protect(payload, False))
        # Publish without replacing a profile even if two instances start together.
        try:
            os.link(candidate, destination)
        except FileExistsError:
            pass
    return True


def discover(local):
    folder = local/'TEC-SGDEA-Consolidado'
    folder.mkdir(parents=True, exist_ok=True)
    profiles = {}
    errors = []
    for key, label in LEGACY.items():
        dest = folder/f'{key}.sqlite3'
        try:
            if copy_vault(local/label/'workspace.sqlite3', dest):
                profiles[label] = (dest, endpoint(dest))
        except (OSError, sqlite3.Error, ValueError, KeyError):
            errors.append(label)
    new = folder/'workspace.sqlite3'
    profiles['Espacio consolidado'] = (new, endpoint(new))
    return profiles, errors
