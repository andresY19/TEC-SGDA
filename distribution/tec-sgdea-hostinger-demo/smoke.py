"""Run from the demo web container, with the synthetic password piped on stdin."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import urllib.request
import uuid

import pikepdf
from sqlalchemy import text
from geology.nucleo.bd import motor
from geology.nucleo.cola import celery_app

assert motor.url.database == 'sgdea_demo' and motor.url.host == 'pg'
code = 'AC-CP-98001'
email, password = sys.stdin.read().splitlines()
token = None


def request(path, body=None, kind='application/json', raw=False):
    headers = {'Content-Type': kind}
    if token:
        headers['Authorization'] = 'Bearer '+token
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080'+path,
                                                      body, headers), timeout=20) as response:
        return response.read() if raw else json.load(response)


assert request('/estado')['estado'] == 'operativo'
assert b'TEC-SGDEA' in request('/app', raw=True)
token = request('/cuentas/ingresar', {'correo':email,'clave':password})['pase']
assert request('/cuentas/yo')['correo'] == email
if '--verify' not in sys.argv:
    item = next(row for row in request('/offline/v1/snapshot')['items'] if row['code']==code)
    buffer = io.BytesIO()
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page()
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
            Type=pikepdf.Name('/Font'), Subtype=pikepdf.Name('/Type1'), BaseFont=pikepdf.Name('/Helvetica'))))
        page.Contents = pdf.make_stream(b'BT /F1 16 Tf 45 700 Td (TEC-SGDEA SINTETICO HOSTINGER) Tj ET')
        pdf.save(buffer)
    data = buffer.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    boundary = uuid.uuid4().hex
    fields = {'operation_id':str(uuid.uuid4()), 'device_id':str(uuid.uuid4()), 'code':code,
              'base_version':item['version'], 'sha256':sha}
    prefix = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
                     for key,value in fields.items())
    body = (prefix+f'--{boundary}\r\nContent-Disposition: form-data; name="pdf"; filename="sintetico.pdf"\r\n'
            'Content-Type: application/pdf\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
    send = lambda: request('/offline/v1/create', body, 'multipart/form-data; boundary='+boundary)
    first, replay = send(), send()
    assert not first['replayed'] and replay['replayed'] and first['id']==replay['id']
assert request('/unidades/'+code)['codigo_carpeta'] == code
assert celery_app.send_task('geology.ping').get(timeout=25)
for _ in range(40):
    with motor.connect() as conn:
        row = conn.execute(text('SELECT ruta,sha256,ruta_matriz,ruta_consulta,error_proceso FROM archivo_digital '
                                'WHERE codigo_carpeta=:code'), {'code':code}).one()
        receipts = conn.execute(text('SELECT count(*) FROM offline_sync_operation')).scalar()
    if row.ruta_matriz and row.ruta_consulta or row.error_proceso:
        break
    time.sleep(2)
assert receipts==1 and hashlib.sha256(Path(row.ruta).read_bytes()).hexdigest()==row.sha256
if row.error_proceso or not row.ruta_matriz or not row.ruta_consulta:
    print('TECHNICAL_PROCESSING_PENDING_OR_FAILED', row.error_proceso)
else:
    for path in (row.ruta_matriz,row.ruta_consulta):
        with pikepdf.open(path) as pdf:
            assert len(pdf.pages)==1
    with pikepdf.open(row.ruta_matriz) as pdf:
        assert pdf.open_metadata().pdfa_status
        print('MATRIX_PROFILE', pdf.open_metadata().pdfa_status)
print('LOGIN_WEB_INVENTORY_CASE_CELERY_SYNC_SHA_PASS', row.sha256)
