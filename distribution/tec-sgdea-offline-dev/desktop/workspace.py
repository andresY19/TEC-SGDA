"""Windows-protected payloads in a persistent SQLite outbox."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

LIMIT = 16 * 1024 * 1024
LEASE = 24 * 3600


class OfflineError(RuntimeError):
    pass


class ConnectionLost(OfflineError):
    pass


class ApiError(OfflineError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, encrypt=True):
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verifier(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Api:
    def __init__(self, url):
        u = urllib.parse.urlsplit(url)
        allowed = u.scheme == 'https' and u.hostname or u.scheme == 'http' and u.hostname == '127.0.0.1' and u.port
        if (not allowed
                or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment):
            raise OfflineError('La dirección del servidor no es válida.')
        self.url = url.rstrip('/')
        self.token = None
        tls = ssl.create_default_context()
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                  urllib.request.HTTPSHandler(context=tls))

    def request(self, path, data=None, content_type='application/json', binary=False, timeout=30):
        headers = {'Content-Type': content_type}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        try:
            with self.opener.open(urllib.request.Request(self.url + path, data=data, headers=headers), timeout=timeout) as r:
                value = r.read(LIMIT + 1)
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read(4096)).get('detail')
            except (ValueError, AttributeError):
                message = None
            raise ApiError(error.code, message if isinstance(message, str) else f'HTTP {error.code}') from None
        except OSError as error:
            raise ConnectionLost('Servidor local no disponible. La cola sigue guardada.') from error
        if len(value) > LIMIT:
            raise OfflineError('Respuesta superior al límite local.')
        return value if binary else json.loads(value)

    def probe(self):
        # The caller uses a separate, unauthenticated API instance for probes.
        result = self.request('/estado', timeout=3)
        if not isinstance(result, dict) or result.get('estado') != 'operativo':
            raise ConnectionLost('El servidor no confirmó su disponibilidad.')

    def login(self, email, password):
        self.token = self.request('/cuentas/ingresar', json.dumps({'correo': email, 'clave': password}).encode())['pase']

    def push(self, row, device):
        boundary = uuid.uuid4().hex
        chunks = []
        fields = {'operation_id': row['id'], 'device_id': device, 'code': row['code'],
                  'base_version': row['version'], 'sha256': row['sha256']}
        for key, value in fields.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="pdf"; filename="documento.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode(),
                       base64.b64decode(row['pdf']), f'\r\n--{boundary}--\r\n'.encode()])
        return self.request('/offline/v1/create', b''.join(chunks), 'multipart/form-data; boundary=' + boundary)


class Workspace:
    def __init__(self, path, url):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS vault (slot TEXT PRIMARY KEY, payload BLOB NOT NULL)')
        self.db.commit()
        self.api = Api(url)
        self.unlocked = False

    def close(self):
        self.api.token = None
        self.db.close()

    def _read(self, slot, default=None):
        row = self.db.execute('SELECT payload FROM vault WHERE slot=?', (slot,)).fetchone()
        return json.loads(protect(row[0], False)) if row else default

    def _write(self, slot, value):
        payload = protect(json.dumps(value, ensure_ascii=False).encode())
        self.db.execute('INSERT INTO vault VALUES (?,?) ON CONFLICT(slot) DO UPDATE SET payload=excluded.payload', (slot, payload))

    def _require(self):
        lease = self._read('lease')
        if not self.unlocked or not lease or not lease['issued'] <= time.time() < lease['expires']:
            raise OfflineError('Habilitación offline vencida o bloqueada. Inicie sesión con conexión.')
        return lease

    def enable(self, email, password):
        previous = self._read('lease')
        if previous and previous['owner'] != email.strip().lower():
            raise OfflineError('Esta base local pertenece a otra cuenta o servidor.')
        self.api.token = None
        try:
            if previous and previous['server'] != self.api.url:
                snapshot = self._upgrade_endpoint(previous, email, password)
            else:
                self.api.login(email, password)
                snapshot = self.api.request('/offline/v1/snapshot')
            if previous and snapshot['owner'] != previous['owner']:
                raise OfflineError('La cuenta del servidor cambió.')
        except Exception:
            self.api.token = None
            raise
        salt = secrets.token_bytes(16)
        now = int(time.time())
        with self.db:
            self._write('lease', {'owner': snapshot['owner'], 'server': self.api.url, 'salt': salt.hex(),
                                  'verify': verifier(password, salt), 'issued': now, 'expires': now + LEASE,
                                  'device': previous['device'] if previous else str(uuid.uuid4())})
            self._write('snapshot', snapshot['items'])
        self.unlocked = True

    def _upgrade_endpoint(self, previous, email, password):
        if (previous['server'], self.api.url) != ('http://127.0.0.1:18098', 'http://127.0.0.1:18099'):
            raise OfflineError('Esta base local pertenece a otro servidor.')
        origin = Api(previous['server'])
        origin.login(email, password)
        before = origin.request('/offline/v1/snapshot')
        # Require the destination to accept the origin's live, revocable session.
        self.api.token = origin.token
        after = self.api.request('/offline/v1/snapshot')
        if before != after:
            raise OfflineError('Los servidores no coinciden. La cola permanece en su perfil original.')
        return after

    def unlock(self, password, email=None):
        lease = self._read('lease')
        compatible = lease and (lease['server'] == self.api.url or
                                (lease['server'], self.api.url) ==
                                ('http://127.0.0.1:18098', 'http://127.0.0.1:18099'))
        if not compatible or (email is not None and lease['owner'] != email.strip().lower()) or not hmac.compare_digest(
            verifier(password, bytes.fromhex(lease['salt'])), lease['verify']
        ):
            raise OfflineError('No se pudo desbloquear el espacio local.')
        self.unlocked = True
        self._require()

    def offline(self):
        self.api.token = None

    def lock(self, revoke=False):
        try:
            if revoke and self.api.token:
                self.api.request('/cuentas/salir', b'')
        finally:
            self.offline()
            self.unlocked = False

    def items(self):
        self._require()
        return self._read('snapshot', [])

    def pending(self):
        self._require()
        return [self._read(slot) for slot, in self.db.execute("SELECT slot FROM vault WHERE slot LIKE 'out:%' ORDER BY rowid")]

    def _item(self, code):
        item = next((x for x in self.items() if x['code'] == code), None)
        if item is None:
            raise OfflineError('Carpeta ausente de la copia autorizada.')
        return item

    def download(self, code):
        self._require()
        if not self.api.token:
            raise OfflineError('Inicie sesión con conexión para descargar.')
        item = self._item(code)
        for doc in item['documents']:
            data = self.api.request(f"/offline/v1/documents/{doc['id']}?sha256={doc['sha256']}", binary=True)
            if sha(data) != doc['sha256']:
                raise OfflineError('SHA-256 de la descarga incorrecto.')
            with self.db:
                self._write('doc:'+str(doc['id']), {'code': code, 'sha256': doc['sha256'], 'pdf': base64.b64encode(data).decode()})
        return len(item['documents'])

    def cached(self, code):
        item = self._item(code)
        result = []
        for doc in item['documents']:
            record = self._read('doc:'+str(doc['id']))
            if record and record['code'] == code and record['sha256'] == doc['sha256']:
                result.append((doc['name'], self.checked_pdf(record)))
        return result

    def cached_count(self, item):
        self._require()
        count = 0
        for doc in item['documents']:
            record = self._read('doc:'+str(doc['id']))
            if record and record['code'] == item['code'] and record['sha256'] == doc['sha256']:
                count += 1
        return count

    @staticmethod
    def checked_pdf(record):
        data = base64.b64decode(record['pdf'], validate=True)
        if sha(data) != record['sha256']:
            raise OfflineError('El SHA-256 del PDF local no coincide.')
        return data

    def dossier(self, code):
        item = self._item(code)
        documents = []
        for doc in item['documents']:
            record = self._read('doc:'+str(doc['id']))
            cached = bool(record and record['code'] == code and record['sha256'] == doc['sha256'])
            documents.append({**doc, 'cached': cached, 'source': 'server'})
        operations = []
        for row in self.pending():
            if row['code'] != code:
                continue
            operations.append({key: value for key, value in row.items() if key != 'pdf'})
            if 'pdf' in row:
                documents.append({'id': row['id'], 'name': row.get('name', 'PDF adjunto'),
                                  'sha256': row['sha256'], 'bytes': row.get('bytes'),
                                  'cached': True, 'source': 'local'})
        return item, documents, operations

    def preview(self, code, document):
        _, documents, _ = self.dossier(code)
        if document not in documents or not document['cached']:
            raise OfflineError('El PDF no está disponible en el inventario autorizado.')
        prefix = 'out:' if document['source'] == 'local' else 'doc:'
        return self.checked_pdf(self._read(prefix+str(document['id'])))

    def new_draft(self, code):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self._new_row(code)
            self._write('out:'+row['id'], row)
        return row['id']

    def _new_row(self, code):
        item = self._item(code)
        if item['state'] is not None or any(row['code'] == code for row in self.pending()):
            raise OfflineError('La carpeta ya existe o tiene una operación local.')
        return {'id': str(uuid.uuid4()), 'code': code, 'version': item['version'], 'state': 'draft'}

    def create(self, code, pdf, name='documento.pdf'):
        if len(pdf) > LIMIT or not pdf.startswith(b'%PDF-'):
            raise OfflineError('Seleccione un PDF de hasta 16 MiB.')
        fingerprint = sha(pdf)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            item = self._item(code)
            rows = self.pending()
            draft = next((row for row in rows if row['code'] == code and row['state'] == 'draft'), None)
            if draft and (item['state'] is not None or draft['version'] != item['version']):
                raise OfflineError('El inventario cambió. El borrador se conserva para revisión.')
            if any(row.get('sha256') == fingerprint for row in rows):
                raise OfflineError('El PDF ya se encuentra en la cola.')
            row = draft or self._new_row(code)
            row.update(sha256=fingerprint, pdf=base64.b64encode(pdf).decode(), state='pending',
                       name=Path(name).name, bytes=len(pdf))
            self._write('out:'+row['id'], row)
        return row['id']

    def work(self, code):
        self._item(code)
        data = self._read('work:'+code)
        if not data:
            raise OfflineError('Actualice la ficha con conexión para habilitar el trabajo local.')
        rows = [r for r in self.pending() if r['code'] == code]
        docs = [{**doc, 'cached': self._read(self._derivative_slot(doc)) is not None}
                for doc in data['documents']]
        return {**data, 'documents': docs, 'operations': [
            {key: value for key, value in row.items() if key != 'pdf'} for row in rows]}

    @staticmethod
    def _derivative_slot(doc):
        return f"derived:{doc['id']}:{doc['kind']}:{doc['sha256']}"

    def refresh_work(self, code, download=False):
        self._item(code)
        if not self.api.token:
            raise OfflineError('Inicie sesión para actualizar los datos del servidor.')
        data = self.api.request(f'/offline/v1/work/{code}')
        with self.db:
            self._write('work:'+code, data)
        if download:
            for doc in data['documents']:
                pdf = self.api.request(f"/offline/v1/derivatives/{doc['id']}/{doc['kind']}?sha256={doc['sha256']}",
                                       binary=True)
                if sha(pdf) != doc['sha256']:
                    raise OfflineError('El SHA-256 del derivado no coincide.')
                with self.db:
                    self._write(self._derivative_slot(doc), {'sha256': doc['sha256'],
                                'pdf': base64.b64encode(pdf).decode()})
        return self.work(code)

    def preview_derivative(self, code, doc):
        if doc not in self.work(code)['documents'] or not doc['cached']:
            raise OfflineError('El derivado no está disponible en la copia local autorizada.')
        return self.checked_pdf(self._read(self._derivative_slot(doc)))

    def save_sheet(self, code, sheet, base_version):
        if not sheet['tramites']:
            raise OfflineError('Agregue al menos un trámite para guardar el avance.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            work = self.work(code)
            if not work['editable'] or work['version'] != base_version:
                raise OfflineError('La versión de la hoja cambió. Abra de nuevo la ficha.')
            prior = next((row for row in reversed(work['operations'])
                          if row.get('kind') == 'sheet'), None)
            if prior and prior['state'] != 'synced':
                if prior.get('attempted') or prior['state'] != 'pending':
                    raise OfflineError('La operación anterior requiere sincronización o revisión.')
                row = prior
            else:
                row = {'id': str(uuid.uuid4()), 'kind': 'sheet', 'code': code,
                       'version': base_version, 'state': 'pending'}
            row.update(sheet=sheet, saved=time.strftime('%Y-%m-%d %H:%M:%S'))
            self._write('out:'+row['id'], row)
        return row['id']

    def sync(self):
        lease = self._require()
        if not self.api.token:
            raise OfflineError('Vuelva a iniciar sesión con conexión antes de sincronizar.')
        for row in self.pending():
            if row['state'] != 'pending':
                continue
            if row.get('kind') == 'sheet':
                self._sync_sheet(row, lease)
                continue
            self.checked_pdf(row)
            try:
                receipt = self.api.push(row, lease['device'])
            except ApiError as error:
                if error.status not in (404, 409, 413, 422):
                    raise
                row.update(state='conflict' if error.status in (404, 409) else 'rejected', error=str(error))
            else:
                if receipt['code'] != row['code'] or receipt['sha256'] != row['sha256']:
                    raise OfflineError('El recibo no corresponde al expediente local.')
                row.update(state='synced', receipt=receipt)
            with self.db:
                self._write('out:'+row['id'], row)
        snapshot = self.api.request('/offline/v1/snapshot')
        if snapshot['owner'] != lease['owner']:
            raise OfflineError('La cuenta del servidor cambió.')
        with self.db:
            self._write('snapshot', snapshot['items'])
        return self.pending()

    def _sync_sheet(self, row, lease):
        row['attempted'] = True
        with self.db:
            self._write('out:'+row['id'], row)
        payload = {**row['sheet'], 'operation_id': row['id'], 'device_id': lease['device'],
                   'base_version': row['version']}
        try:
            receipt = self.api.request(f"/offline/v1/work/{row['code']}/sheet",
                                       json.dumps(payload, ensure_ascii=False).encode())
        except ApiError as error:
            if error.status not in (404, 409, 422):
                raise
            row.update(state='conflict' if error.status in (404, 409) else 'rejected', error=str(error))
        else:
            if receipt['operation_id'] != row['id'] or receipt['code'] != row['code']:
                raise OfflineError('El recibo no corresponde a la hoja local.')
            row.update(state='synced', receipt=receipt)
        with self.db:
            self._write('out:'+row['id'], row)
        if row['state'] == 'synced':
            self.refresh_work(row['code'])
