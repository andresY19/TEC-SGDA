"""Exercise the Windows workspace across restarts and a lost sync response."""
import argparse
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
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
from workspace import ApiError, OfflineError, Workspace, sha
from pdf_viewer import rasterize

P = 'geology-tec-sgdea-pilot-a01'
URL = os.getenv('TEC_SGDEA_TEST_URL', 'http://127.0.0.1:18098')


def docker(*args, data=None):
    p = subprocess.run(['docker', *args], input=data, capture_output=True, check=True)
    return p.stdout


def sql(query):
    return docker('exec', P+'-pg', 'psql', '-XAtq', '-v', 'ON_ERROR_STOP=1',
                  '-U', 'geology', '-d', 'geology', '-c', query).decode().splitlines()


def credentials(root):
    _, email, password = (root/'acceso-local.txt').read_text(encoding='utf-8').splitlines()
    return email.removeprefix('Correo: '), password.removeprefix('Contraseña: ')


def ready():
    for _ in range(40):
        try:
            with urllib.request.urlopen(URL+'/estado', timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError('Web del piloto no disponible')


def phase(root, session, action):
    fixture = json.loads((session/'fixture.json').read_text())
    email, password = credentials(root)
    with_session = Workspace(session/'cache.sqlite3', URL)
    try:
        if action == 'online':
            with_session.enable(email, password)
            assert with_session.download('AC-CP-99001') == 1
            assert with_session.cached('AC-CP-99001')
        elif action == 'offline':
            with_session.unlock(password)
            assert with_session.api.token is None
            code = fixture['created']
            ident = with_session.new_draft(code)
            assert with_session.dossier(code)[2][0]['state'] == 'draft'
            try:
                with_session.new_draft(code)
            except OfflineError:
                pass
            else:
                raise AssertionError('Se duplicó el borrador')
            print('DRAFT_SAVED', ident)
        elif action == 'attach':
            with_session.unlock(password)
            code = fixture['created']
            draft, = with_session.dossier(code)[2]
            assert draft['state'] == 'draft'
            for key, file in [('created', 'new.pdf'), ('conflict', 'stale.pdf')]:
                ident = with_session.create(fixture[key], (session/file).read_bytes(), file)
                if key == 'created':
                    assert ident == draft['id']
            print('DRAFT_REOPEN_ATTACH_PASS')
        else:
            with_session.unlock(password)
            pending = with_session.pending()
            assert len(pending) == 2 and all(row['state']=='pending' for row in pending)
            assert with_session.cached('AC-CP-99001')
            _, documents, operations = with_session.dossier(fixture['created'])
            assert documents[0]['source'] == 'local' and operations[0]['state'] == 'pending'
            data = with_session.preview(fixture['created'], documents[0])
            rendered, total = rasterize(data, 0, 800)
            assert total == 1 and max(rendered.size) <= 801 and rendered.getextrema()[0][0] < 255
            try:
                rasterize(b'%PDF- corrupt', 0, 800)
            except OfflineError:
                pass
            else:
                raise AssertionError('El visor aceptó un PDF corrupto')
            print('RESTART_PERSISTENCE_PASS')
            if action == 'restart':
                return
            with_session.enable(email, password)
            if action == 'interrupt':
                push = with_session.api.push
                def lose_response(row, device):
                    assert row['code'] == fixture['created']
                    assert push(row, device)['replayed'] is False
                    raise OfflineError('Respuesta de sincronización perdida en el ensayo.')
                with_session.api.push = lose_response
                try:
                    with_session.sync()
                except OfflineError:
                    assert all(row['state']=='pending' for row in with_session.pending())
                else:
                    raise AssertionError('La pérdida de respuesta no se simuló')
                print('LOST_ACK_PENDING_PASS')
                return
            results = {row['code']:row for row in with_session.sync()}
            success, conflict = results[fixture['created']], results[fixture['conflict']]
            assert success['state']=='synced' and success['receipt']['replayed'] and conflict['state']=='conflict', [success['state'],conflict['state']]
            assert with_session.download(fixture['created']) == 1
            assert sha(with_session.cached(fixture['created'])[0][1]) == success['sha256']
            _, docs, _ = with_session.dossier(fixture['created'])
            server_pdf = next(doc for doc in docs if doc['source'] == 'server')
            assert sha(with_session.preview(fixture['created'], server_pdf)) == success['sha256']
            lease = with_session._require()
            assert with_session.api.push(success, lease['device'])['replayed']
            for modified, status in [
                ({**success, 'sha256':'0'*64},422),
                ({**success, 'device':'different'},409),
                ({**success, 'id':fixture['different_uuid']},409),
            ]:
                try:
                    with_session.api.push(modified, fixture['different_uuid'] if 'device' in modified else lease['device'])
                except ApiError as e:
                    assert e.status==status, e.status
                else:
                    raise AssertionError('Se aceptó una operación inválida')
            web = with_session.api.request('/unidades/'+fixture['created'])
            assert web['codigo_carpeta']==fixture['created'] and web['estado']=='En cola'
            (session/'result.json').write_text(json.dumps({'code':fixture['created'],'sha256':success['sha256'],
                'receipt':success['receipt'],'conflict':fixture['conflict'],'conflict_preserved':True,
                'replayed':True,'web_query':True,'download_sha256_verified':True,
                'draft_reopen':True,'local_pdf_render':True,'corrupt_pdf_rejected':True},indent=2))
    finally:
        with_session.close()


def execute(root):
    import uuid
    web = json.loads(docker('inspect', P+'-web'))[0]
    assert web['Config']['Labels']['com.docker.compose.project']==P
    assert web['HostConfig']['PortBindings']=={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'18098'}]}
    session = root / ('e2e-'+uuid.uuid4().hex[:12])
    session.mkdir()
    fixture = dict(zip(['created','conflict'],['AC-CP-'+str(n) for n in secrets.SystemRandom().sample(range(97000,98000),2)]))
    fixture['different_uuid'] = str(uuid.uuid4())
    (session/'fixture.json').write_text(json.dumps(fixture))
    for k,file in [('created','new.pdf'),('conflict','stale.pdf')]:
        code=fixture[k]
        sql("INSERT INTO inventario_origen(codigo_carpeta,caja_origen,periodo,folios,asunto) VALUES ('"+code+"','SINTETICO SGDEA','I',1,'Piloto offline "+code+"')")
        pdf = """import pikepdf,sys
with pikepdf.Pdf.new() as pdf:
 page=pdf.add_blank_page(page_size=(595,842))
 page.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name('/Font'),Subtype=pikepdf.Name('/Type1'),BaseFont=pikepdf.Name('/Helvetica'))))
 page.Contents=pdf.make_stream(b'BT /F1 18 Tf 55 740 Td (TEC-SGDEA SINTETICO CODE) Tj ET')
 pdf.docinfo['/Title']='TEC-SGDEA SINTETICO CODE'
 pdf.save(sys.stdout.buffer)
""".replace('CODE',code)
        (session/file).write_bytes(docker('exec',P+'-web','python','-B','-c',pdf))
    def child(mode):
        subprocess.run([sys.executable,'-B',__file__,str(root),'--session',str(session),'--phase',mode],check=True)
    child('online')
    child('offline')
    child('attach')
    child('restart')
    raw=(session/'cache.sqlite3').read_bytes()
    assert b'%PDF-' not in raw and b'Piloto offline' not in raw and fixture['created'].encode() not in raw
    sql("UPDATE inventario_origen SET asunto='Cambio remoto sintetico' WHERE codigo_carpeta='"+fixture['conflict']+"'")
    child('interrupt')
    assert sql("SELECT count(*) FROM offline_sync_operation WHERE codigo_carpeta='"+fixture['created']+"'")==['1']
    child('sync')
    assert sql("SELECT count(*) FROM offline_sync_operation WHERE codigo_carpeta='"+fixture['created']+"'")==['1']
    assert sql("SELECT count(*) FROM unidad_documental WHERE codigo_carpeta='"+fixture['conflict']+"'")==['0']
    for _ in range(50):
        trace=sql("SELECT coalesce(ruta_matriz,'')<>'' AND coalesce(ruta_consulta,'')<>'' FROM archivo_digital WHERE codigo_carpeta='"+fixture['created']+"'")
        if trace==['t']:
            break
        time.sleep(1)
    else:
        raise AssertionError('Celery no completó los derivados')
    result=json.loads((session/'result.json').read_text())
    result.update(celery_derivatives=True, protected_sql_rows=verify_original_sql(root),protected_files=verify_files(root))
    (session/'result.json').write_text(json.dumps(result,indent=2))
    print('E2E_PASS', session)


def verify_original_sql(root):
    baseline=json.loads((root/'restore-logical.json').read_text())['postgres']
    count=0
    for table,expected in baseline['rows'].items():
        assert re.fullmatch('[a-z_]+',table)
        conditions={
            'inventario_origen':"WHERE caja_origen IS DISTINCT FROM 'SINTETICO SGDEA'",
            'cuenta':"WHERE correo <> 'admin.tecarchiva.dev@example.invalid' AND nombre IS DISTINCT FROM 'SINTETICO SGDEA CONSULTA'",
            'unidad_documental':"WHERE codigo_carpeta NOT IN (SELECT codigo_carpeta FROM inventario_origen WHERE caja_origen='SINTETICO SGDEA')",
            'archivo_digital':"WHERE codigo_carpeta NOT IN (SELECT codigo_carpeta FROM inventario_origen WHERE caja_origen='SINTETICO SGDEA')",
            'asiento_hoja':"WHERE expediente_id NOT IN (SELECT id FROM unidad_documental WHERE codigo_carpeta IN (SELECT codigo_carpeta FROM inventario_origen WHERE caja_origen='SINTETICO SGDEA'))",
            'trazabilidad':"WHERE expediente_id NOT IN (SELECT id FROM unidad_documental WHERE codigo_carpeta IN (SELECT codigo_carpeta FROM inventario_origen WHERE caja_origen='SINTETICO SGDEA'))"
        }
        values=sql(f"SELECT row_to_json(r)::text FROM (SELECT * FROM public.{table} {conditions.get(table,'')}) r ORDER BY row_to_json(r)::text")
        assert len(values)==expected['count'] and hashlib.sha256('\n'.join(values).encode()).hexdigest()==expected['sha256'],table
        count+=len(values)
    return count


def verify_files(root):
    expected={k:v['sha256'] for k,v in json.loads((root/'file-index.json').read_text()).items()
              if k.split('/')[0] in ('deposito','expedidos','datos')}
    probe="""from pathlib import Path
import hashlib
assert all(hashlib.sha256((Path('/srv/geology')/key).read_bytes()).hexdigest()==value for key,value in expected.items())
"""
    docker('exec',P+'-web','python','-B','-c','expected='+repr(expected)+'\n'+probe)
    return len(expected)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--session',type=Path)
    parser.add_argument('--phase')
    args=parser.parse_args()
    if args.phase:
        phase(args.root,args.session,args.phase)
    else:
        execute(args.root)
