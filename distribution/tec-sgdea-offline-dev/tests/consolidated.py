"""Verify migration of independent vaults and the receipt bootstrap."""
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import uuid

from e2e_windows import credentials, docker, sql, verify_files, verify_original_sql
from migration import CURRENT_SERVER, discover, endpoint
from workspace import ApiError, Workspace, sha


OLD = 'http://127.0.0.1:18098'


def receipt_bootstrap():
    script = (Path(__file__).resolve().parents[1]/'backend/work_bootstrap.sql').read_text()
    command = ('exec','-i','geology-tec-sgdea-pilot-a01-pg','psql','-Xq','-v','ON_ERROR_STOP=1',
               '-U','geology','-d','geology')
    namespace = 'verify_receipts_'+uuid.uuid4().hex
    body = script.removeprefix('BEGIN;\n').removesuffix('COMMIT;\n')
    docker(*command, data=(f'BEGIN; CREATE SCHEMA {namespace}; SET LOCAL search_path={namespace},public;\n'
                           +body+body+'ROLLBACK;\n').encode())
    before = sql('SELECT operation_id, fingerprint, estado FROM offline_sheet_receipt ORDER BY operation_id')
    for _ in range(2):
        docker(*command, data=script.encode())
    assert sql('SELECT operation_id, fingerprint, estado FROM offline_sheet_receipt ORDER BY operation_id') == before
    assert sql(f"SELECT count(*) FROM pg_namespace WHERE nspname='{namespace}'")==['0']


def run(root, output):
    output.mkdir()
    fixtures = output/'perfiles-sinteticos'
    fixtures.mkdir()
    email, password = credentials(root)
    code = 'AC-CP-'+str(secrets.randbelow(900)+96000)
    sql(f"INSERT INTO inventario_origen(codigo_carpeta,caja_origen,periodo,folios,asunto) "
        f"VALUES ('{code}','SINTETICO SGDEA','I',1,'Consolidación sintética {code}')")
    source_hashes = {}
    pdf_source = """import sys,pikepdf
with pikepdf.Pdf.new() as pdf:
    page=pdf.add_blank_page()
    page.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
        Type=pikepdf.Name('/Font'),Subtype=pikepdf.Name('/Type1'),BaseFont=pikepdf.Name('/Helvetica'))))
    page.Contents=pdf.make_stream(b'BT /F1 16 Tf 50 700 Td (TEC-SGDEA CONSOLIDACION SINTETICA CODE) Tj ET')
    pdf.save(sys.stdout.buffer)
""".replace('CODE',code)
    pdf = docker('exec','geology-tec-sgdea-pilot-a01-web','python','-B','-c',pdf_source)
    expected = {}
    for name, server in [('Preview', OLD), ('Fichas', OLD), ('Trabajo', CURRENT_SERVER)]:
        file = fixtures/f'TEC-SGDEA-{name}'/'workspace.sqlite3'
        vault = Workspace(file, server)
        try:
            vault.enable(email, password)
            vault.offline()
            operation = vault.create(code, pdf) if name=='Preview' else vault.new_draft(code)
            expected[name] = (operation, vault._require()['device'])
        finally:
            vault.close()
        source_hashes[file] = hashlib.sha256(file.read_bytes()).hexdigest()
    profiles, errors = discover(fixtures)
    assert not errors and len(profiles)==4
    for name, (operation, device) in expected.items():
        target, server = profiles['TEC-SGDEA-'+name]
        vault = Workspace(target, server)
        try:
            vault.unlock(password)
            row, = vault.pending()
            assert row['id']==operation and vault._require()['device']==device
            if name=='Preview':
                assert sha(vault.preview(code,vault.dossier(code)[1][0]))==sha(pdf)
        finally:
            vault.close()
    target, _ = profiles['TEC-SGDEA-Preview']
    vault = Workspace(target, CURRENT_SERVER)
    try:
        vault.enable(email, password)
        assert vault._require()['device']==expected['Preview'][1]
        row, = vault.sync()
        assert row['state']=='synced' and row['id']==expected['Preview'][0]
        assert vault.api.push(row, vault._require()['device'])['replayed']
        try:
            vault.api.push({**row,'version':'0'*64},vault._require()['device'])
        except ApiError as error:
            assert error.status==409
        else:
            raise AssertionError('Se aceptó un cambio en un recibo existente')
        assert vault.api.request('/unidades/'+code)['codigo_carpeta']==code
    finally:
        vault.close()
    assert endpoint(target)==CURRENT_SERVER
    assert discover(fixtures)[0]['TEC-SGDEA-Preview']==(target,CURRENT_SERVER)
    assert all(hashlib.sha256(file.read_bytes()).hexdigest()==expected
               for file,expected in source_hashes.items())
    with sqlite3.connect(target) as db:
        assert b'%PDF-' not in b''.join(payload for payload, in db.execute('SELECT payload FROM vault'))
    receipt_bootstrap()
    result = {'code':code, 'profiles_copied':3,'sources_unchanged':True, 'same_device_and_uuid':True,
              'restart_offline':True,'sha256':sha(pdf),'endpoint_upgrade':True,'retry_idempotent':True,
              'modified_retry_rejected':True,'bootstrap_clean_and_repeatable':True,
              'protected_sql_rows':verify_original_sql(root),'protected_files':verify_files(root)}
    (output/'result.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    run(*map(Path,sys.argv[1:]))
