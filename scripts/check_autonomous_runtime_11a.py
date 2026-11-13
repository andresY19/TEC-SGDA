"""Normal runtime tests; streamed to the isolated runner, never mounted as source."""
from pathlib import Path
import hashlib
import json
import os
import unittest
import urllib.request
import uuid

from geology.nucleo.cola import celery_app
from geology.nucleo.bd import SesionLocal
from geology.modelos import Archivo
from geology.dominio import pdfa_controlado as p

assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11a-')
ROOT=Path('/cert')


class AutonomousRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures=json.loads((ROOT/'fixtures.json').read_text())
        cls.results={}
        cls.protected=json.loads((ROOT/'fixture-hashes.json').read_text())

    def test_01_nonroot_and_embedded_source(self):
        self.assertEqual(os.getuid(),10001);self.assertEqual(os.getgid(),10001)
        manifest=json.loads(Path('/opt/geology-distribution/build-manifest.json').read_text())
        self.assertTrue(all(p.huella(Path('/srv/geology')/n)==sha for n,sha in manifest['source_sha256'].items()))
        self.assertFalse(os.access('/srv/geology/geology/main.py',os.W_OK))
        self.assertFalse(Path('/srv/geology/.env').exists())

    def test_02_http(self):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path in ['/estado','/app','/openapi.json']:
            with opener.open('http://web:8080'+path,timeout=10) as response:
                self.assertEqual(response.status,200)
                body=response.read()
                if path=='/estado':self.assertEqual(json.loads(body)['estado'],'operativo')
                if path=='/openapi.json':self.assertEqual(json.loads(body)['info']['version'],'2.13.0')

    def test_03_ping_standard_worker(self):
        result=celery_app.send_task('geology.ping',task_id=str(uuid.uuid4()),queue=os.environ['GEOLOGY_COLA'])
        self.assertEqual(result.get(timeout=30),'pong')
        self.results['ping']={'id':result.id,'state':result.state,'value':'pong'}

    def convert(self,name,profile):
        with SesionLocal() as s:
            row=s.get(Archivo,self.fixtures[name]['id'])
            old={x:p.huella(Path(x)) for x in [row.ruta_matriz,row.ruta_consulta]}
        result=celery_app.send_task('geology.preparar_digitalizacion',args=[self.fixtures[name]['id']],
            kwargs={'perfil_solicitado':profile},task_id=str(uuid.uuid4()),queue=os.environ['GEOLOGY_COLA'])
        value=result.get(timeout=180);self.assertEqual(result.state,'SUCCESS')
        self.assertEqual(value['perfil'],profile)
        for derivative in value['resultados']:
            path=Path(derivative['ruta']);self.assertNotIn(str(path),old)
            self.assertTrue(p.validar(path,profile)['conforme'])
            self.assertEqual(p.huella(path),derivative['sha256'])
            self.assertEqual(p.contenido(path),p.contenido(Path(self.fixtures[name]['source'])))
            xml=Path(derivative['informe']);self.assertEqual(p.huella(xml),derivative['informe_sha256'])
            events=[x for x in xml.parent.glob('evento-*.json') if json.loads(x.read_text())['estado']=='validado_publicado']
            self.assertEqual(len(events),1);self.assertTrue(p.verificar_diario(events[0])['verificado'])
        self.assertTrue(all(p.huella(Path(path))==sha for path,sha in old.items()))
        with SesionLocal() as s:
            row=s.get(Archivo,self.fixtures[name]['id'])
            self.assertEqual(row.ruta_matriz,value['matriz']);self.assertEqual(row.ruta_consulta,value['consulta'])
        self.results[name]={'id':result.id,'state':result.state,'return':value,'previous_derivatives_preserved':old}

    def test_04_pdfa_1b_standard_worker(self):self.convert('explicit_1b','1b')
    def test_05_pdfa_2b_standard_worker(self):self.convert('explicit_2b','2b')

    def test_06_persistence_and_no_missing_references(self):
        self.assertTrue(all(p.huella(Path(path))==sha for path,sha in self.protected.items()))
        with SesionLocal() as s:
            rows=s.query(Archivo).all();self.assertEqual(len(rows),9)
            for a in rows:
                for path in [a.ruta,a.ruta_matriz,a.ruta_consulta]:self.assertTrue(Path(path).is_file())

    @classmethod
    def tearDownClass(cls):
        with (ROOT/'results/normal-runtime.json').open('x') as f:json.dump(cls.results,f,indent=2)


if __name__=='__main__':unittest.main(verbosity=2)
