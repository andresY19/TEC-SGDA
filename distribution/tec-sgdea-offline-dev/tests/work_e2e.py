"""Synthetic sheet, processing and trace certification for the local work API."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from e2e_windows import URL, credentials, sql, verify_files, verify_original_sql
from workspace import Api, ApiError, ConnectionLost, OfflineError, Workspace, sha
from pdf_viewer import rasterize


def phase(root, output, code, mode):
    email, password = credentials(root)
    filename = 'stale.sqlite3' if mode in ('stale', 'conflict') else os.getenv(
        'TEC_SGDEA_TEST_WORKSPACE', 'work.sqlite3')
    workspace = Workspace(output/filename, URL)
    try:
        if mode in ('cache', 'stale'):
            workspace.enable(email, password)
            data = workspace.refresh_work(code, download=mode=='cache')
            assert data['editable'] and data['processing'][0]['processed']
            assert data['trace']
            assert {d['kind'] for d in data['documents']} == {'matriz','consulta'}
        if mode in ('edit','stale'):
            workspace.unlock(password)
            workspace.offline()
            data = workspace.work(code)
            sheet = {**data['sheet'], 'nombre_expediente': 'TEC-SGDEA AVANCE SINTETICO '+code,
                     'tramites': [{'tipo_documental':'Borrador inicial', 'folio_desde':'1', 'folio_hasta':'1'}]}
            if mode == 'edit':
                for doc in data['documents']:
                    pdf = workspace.preview_derivative(code, doc)
                    assert sha(pdf) == doc['sha256'] and rasterize(pdf, 0, 480)[1] == 1
            first = workspace.save_sheet(code, sheet, data['version'])
            sheet['tramites'][0]['tipo_documental'] = 'Trámite sintético editado'
            assert workspace.save_sheet(code, sheet, data['version']) == first
            return
        if mode == 'expiry':
            workspace.unlock(password)
            lease = workspace._require()
            with patch('workspace.time.time', return_value=lease['issued']+23*3600):
                row, = workspace.pending()
                assert row['state']=='pending'
                for document in workspace.work(code)['documents']:
                    assert sha(workspace.preview_derivative(code, document))==document['sha256']
            with patch('workspace.time.time', return_value=lease['issued']+25*3600):
                for action in (lambda: workspace.unlock(password), workspace.pending):
                    try:
                        action()
                    except OfflineError:
                        pass
                    else:
                        raise AssertionError('La habilitación vencida permitió el acceso')
            return
        if mode in ('interrupt','sync','conflict'):
            workspace.unlock(password)
            queued, = workspace.pending()
            assert queued['state']=='pending' and queued['sheet']['tramites'][0]['tipo_documental']=='Trámite sintético editado'
            workspace.enable(email, password)
            if mode == 'interrupt':
                request = workspace.api.request

                def lose(path, data=None, **kwargs):
                    reply = request(path, data, **kwargs)
                    if path.endswith('/sheet'):
                        assert not reply['replayed']
                        raise ConnectionLost('Respuesta perdida tras guardar avance')
                    return reply

                workspace.api.request = lose
                try:
                    workspace.sync()
                except ConnectionLost:
                    assert workspace.pending()[0]['attempted']
                    return
                raise AssertionError('No se simuló pérdida de respuesta')
            result, = workspace.sync()
            assert result['id'] == queued['id']
            if mode == 'conflict':
                assert result['state']=='conflict' and result['sheet']==queued['sheet']
                return
            assert result['state']=='synced' and result['receipt']['replayed']
            web = workspace.api.request('/unidades/'+code)
            assert web['estado']==result['receipt']['estado'] and web['reviso_hoja'] is None
            assert web['nombre_expediente']==queued['sheet']['nombre_expediente']
            assert web['tramites'][0]['tipo_documental']=='Trámite sintético editado'
            assert sum(t['accion']=='guardar_avance' for t in workspace.work(code)['trace'])==1
            assert sql("SELECT count(*) FROM offline_sheet_receipt WHERE operation_id='"+queued['id']+"'")==['1']
            assert workspace.work(code)['operations'][0]['state']=='synced'
    finally:
        workspace.close()


def run(root, session, output):
    code = json.loads((session/'result.json').read_text())['code']
    output.mkdir(exist_ok=True)
    assert sql(f"SELECT caja_origen FROM inventario_origen WHERE codigo_carpeta='{code}'")==['SINTETICO SGDEA']
    for mode in ('cache','edit','expiry','stale','interrupt','sync','conflict'):
        subprocess.run([sys.executable,'-B',__file__,str(root),str(session),str(output),code,mode], check=True)
        print(mode+'_PASS', flush=True)
    with sqlite3.connect(output/'work.sqlite3') as database:
        payloads = b''.join(blob for blob, in database.execute('SELECT payload FROM vault'))
    assert b'%PDF-' not in payloads and b'AVANCE SINTETICO' not in payloads
    try:
        Api(URL).request('/offline/v1/work/'+code)
    except ApiError as error:
        assert error.status==401
    else:
        raise AssertionError('Acceso anónimo a trabajo offline')
    result = {'code':code, 'expected_sheet':'TEC-SGDEA AVANCE SINTETICO '+code, 'derivatives_verified':2,
              'restart':True, 'lost_ack_replayed':True, 'conflict_preserved':True, 'server_trace':True,
              'dpapi_payload':True, 'anonymous_denied':True, 'lease_23h_25h_simulated':True,
              'protected_sql_rows':verify_original_sql(root), 'protected_files':verify_files(root)}
    (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__=='__main__':
    root, session, output = map(Path, sys.argv[1:4])
    if len(sys.argv)==6:
        phase(root, output, *sys.argv[4:])
    else:
        run(root, session, output)
