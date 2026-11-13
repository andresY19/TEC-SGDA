"""HTTP real y reinicio exclusivo autorizado; sin usuarios ni datos de aplicación."""
import hashlib,json,os,subprocess,time,unittest,urllib.request
from pathlib import Path

PROJECT='geology-local-20261106-57a99a'
ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('GEOLOGY_HTTP_INTEGRATION')=='local-approved','HTTP local explícito')
class HTTPLocal(unittest.TestCase):
    def get(self,path):
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8080'+path,timeout=5) as f:
            return f.status,f.read()

    def schema(self):
        raw=subprocess.check_output(['docker','exec',PROJECT+'-almacen_datos-1','pg_dump','-U','geology','-d','geology',
            '--schema-only','--no-owner','--no-acl'],text=True)
        return hashlib.sha256('\n'.join(x for x in raw.splitlines() if not x.startswith(('\\restrict','\\unrestrict'))).encode()).hexdigest()

    def test_01_http_interfaz_y_rutas(self):
        status,body=self.get('/estado');self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['estado'],'operativo')
        status,body=self.get('/app');self.assertEqual(status,200);self.assertIn(b'GEOLOGY',body)
        status,body=self.get('/openapi.json');self.assertGreater(len(json.loads(body)['paths']),100)

    def test_02_reinicio_sin_cambiar_esquema(self):
        server=PROJECT+'-servidor-1'
        c=json.loads(subprocess.check_output(['docker','inspect',server],text=True))[0]
        self.assertEqual(c['Config']['Labels']['com.docker.compose.project'],PROJECT)
        antes=self.schema()
        subprocess.run(['docker','restart','--time','10',server],capture_output=True,text=True,check=True)
        operativo=False
        for _ in range(30):
            try:
                if json.loads(self.get('/estado')[1])['estado']=='operativo':operativo=True;break
            except Exception:pass
            time.sleep(1)
        self.assertTrue(operativo)
        despues=self.schema();self.assertEqual(antes,despues)
        inicial=json.loads((ROOT/'phase8b-schema-before-http.json').read_text())['sha256']
        self.assertEqual(antes,inicial)
        (ROOT/'phase8b-restart-evidence.json').write_text(json.dumps({'before_first_http':inicial,
            'before_restart':antes,'after_restart':despues,'unchanged':True},indent=2),encoding='utf-8')

    def test_03_solo_servicios_autorizados(self):
        names=subprocess.check_output(['docker','ps','--filter','label=com.docker.compose.project='+PROJECT,
            '--format','{{.Label "com.docker.compose.service"}}'],text=True).splitlines()
        self.assertEqual(set(names),{'almacen_datos','mensajeria','servidor'})


if __name__=='__main__':unittest.main()
