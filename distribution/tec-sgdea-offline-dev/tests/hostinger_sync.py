"""Exercise the Windows DPAPI workspace against the TLS-only synthetic demo."""
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop'))
from server_policy import HOSTINGER_DEMO
from workspace import Api, ApiError, Workspace, sha

output = Path(sys.argv[1])
database = output/'sync-validation.sqlite3'
email, password = os.environ['SGDEA_TEST_USER'], os.environ['SGDEA_TEST_PASS']
code = 'AC-CP-98003'
try:
    Api(HOSTINGER_DEMO).request('/offline/v1/snapshot')
except ApiError as error:
    assert error.status == 401
else:
    raise AssertionError('Anonymous sync accepted')

ws = Workspace(database, HOSTINGER_DEMO)
try:
    ws.enable(email, password)
    assert ws.download(code)==1
    data = ws.refresh_work(code)
    original = ws.cached(code)[0][1]
    expected = sha(original)
    assert expected == next(item for item in ws.items() if item['code']==code)['documents'][0]['sha256']
    ws.offline()
    operation = ws.save_sheet(code, {**data['sheet'], 'nombre_expediente':'Avance sintético Windows HTTPS',
        'tramites':[{'tipo_documental':'Prueba de sincronización por HTTPS'}]},data['version'])
finally:
    ws.close()
ws = Workspace(database, HOSTINGER_DEMO)
try:
    ws.unlock(password, email)
    assert ws.api.token is None and sha(ws.cached(code)[0][1])==expected
    pending, = ws.pending()
    assert pending['id']==operation and pending['state']=='pending'
    ws.enable(email, password)
    row, = ws.sync()
    assert row['state']=='synced' and row['id']==operation
    payload = {**row['sheet'], 'operation_id':operation, 'device_id':ws._require()['device'],
               'base_version':row['version']}
    replay=ws.api.request(f'/offline/v1/work/{code}/sheet',json.dumps(payload).encode())
    assert replay['replayed'] and replay['operation_id']==operation
    result=ws.api.request('/unidades/'+code)
    assert result['nombre_expediente']=='Avance sintético Windows HTTPS'
    ws.lock(revoke=True)
finally:
    ws.close()
(output/'windows-sync.json').write_text(json.dumps({'code':code,'https':True,'offline_restart':True,
    'sha256':expected,'synchronized':True,'replayed':True,'anonymous_rejected':True},indent=2))
