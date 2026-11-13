"""Additional API checks on the local pilot after the vertical test."""
import json
from pathlib import Path
import secrets
import sys
import uuid

from e2e_windows import P, URL, credentials, docker, sql, verify_files
from workspace import Api, ApiError, Workspace


def denied(action, expected):
    try:
        action()
    except ApiError as error:
        assert error.status == expected, error.status
    else:
        raise AssertionError(f'Expected HTTP {expected}')


def run(root, session):
    result = json.loads((session/'result.json').read_text())
    original = Api(URL)
    denied(lambda: original.request('/offline/v1/snapshot'), 401)
    email, password = credentials(root)
    workspace = Workspace(session/'cache.sqlite3', URL)
    try:
        workspace.enable(email,password)
        success = next(x for x in workspace.pending() if x['state']=='synced')
        current = next(x for x in workspace.items() if x['code']==result['conflict'])
        duplicate = {**success,'id':str(uuid.uuid4()),'code':current['code'],'version':current['version']}
        denied(lambda: workspace.api.push(duplicate, workspace._require()['device']),409)
        assert sql("SELECT count(*) FROM unidad_documental WHERE codigo_carpeta='"+current['code']+"'")==['0']
        downloaded = next(x for x in workspace.items() if x['code']==success['code'])['documents'][0]
        denied(lambda: workspace.api.request(f"/offline/v1/documents/{downloaded['id']}?sha256="+'0'*64,binary=True),409)
        workspace.api.request('/cuentas/salir',b'')
        denied(lambda: workspace.api.push(success, workspace._require()['device']),401)
        lookup = 'consulta-sgdea-'+uuid.uuid4().hex[:8]+'@example.invalid'
        pwd = secrets.token_urlsafe(30)
        source="""from geology.modelos import UsuarioBD,cifrar_clave
from geology.nucleo.bd import SesionLocal
with SesionLocal.begin() as s:
 s.add(UsuarioBD(nombre='SINTETICO SGDEA CONSULTA',correo=email,rol='consulta',funcion='Ambas',activo=True,debe_cambiar_clave=False,clave_hash=cifrar_clave(password)))
"""
        docker('exec','-i',P+'-web','python','-B','-',data=('email,password='+repr((lookup,pwd))+'\n'+source).encode())
        reader=Api(URL)
        reader.login(lookup,pwd)
        denied(lambda: reader.request('/offline/v1/snapshot'),403)
        if URL.endswith(':18099'):
            denied(lambda: reader.request('/offline/v1/work/'+success['code']),403)
            denied(lambda: reader.request('/offline/v1/work/'+success['code']+'/sheet', b'{}'),403)
        denied(lambda: reader.push(success,workspace._require()['device']),403)
        denied(lambda: reader.request(f"/offline/v1/documents/{downloaded['id']}?sha256={downloaded['sha256']}",binary=True),403)
        assert verify_files(root)==63
    finally:
        workspace.close()
    print('SECURITY_PASS', 9 if URL.endswith(':18099') else 7)


if __name__=='__main__':
    run(Path(sys.argv[1]),Path(sys.argv[2]))
