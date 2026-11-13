"""Primer flujo HTTP con fixtures SINTETICO 9A; sin IA ni aprobaciÃƒÂ³n ISAD(G).

Ejecutar una vez en destino local aprobado. Conserva fixtures y diarios para
auditorÃƒÂ­a; no borra datos. ContraseÃƒÂ±as y pase ÃƒÂºnicamente en memoria.
"""
import os,json,secrets,hashlib,io,time,unittest,urllib.request,urllib.error
from pathlib import Path
from datetime import date
import pikepdf
from sqlalchemy import select,inspect
from sqlalchemy.exc import IntegrityError
from geology.nucleo.bd import Base,motor,SesionLocal,registrar_modelos
from geology.modelos import (UsuarioBD,cifrar_clave,clave_correcta,Fondo,Periodo,Seccion,Serie,Subserie,
    UnidadInventario,Expediente,Archivo,Trazabilidad,Tramite)
from geology.rutas.cuentas import CuentaNueva,_validar_rol_y_funcion,_a_usuario
from geology.dominio.estados import Rol,Estado
from geology.dominio.division import PAGINAS_POR_PARTE

CODIGOS=('AC-CP-99001','AC-CP-99002')
EMAIL='documentos.9a@example.invalid'
ROOT=Path('/srv/geology')
OUT=ROOT/'expedidos'/'pruebas_sinteticas_9a'
HTTP_BASE=os.environ.get('GEOLOGY_E2E_HTTP_BASE','http://127.0.0.1:8080')


def huella(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def filas_previas():
    with motor.connect() as c:
        return {t.name:[dict(x) for x in c.execute(select(t)).mappings()] for t in Base.metadata.sorted_tables}


def resumen_previas(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()


def crear_pdf(path,paginas):
    with pikepdf.Pdf.new() as pdf:
        font=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name('/Font'),Subtype=pikepdf.Name('/Type1'),BaseFont=pikepdf.Name('/Helvetica')))
        for i in range(paginas):
            page=pdf.add_blank_page(page_size=(612,792))
            page.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            content=f'BT /F1 12 Tf 50 720 Td (SINTETICO FASE9A PAGINA {i+1} - 2001-{min(i+1,12):02d}-01) Tj ET'
            page.Contents=pdf.make_stream(content.encode('ascii'))
        pdf.docinfo['/Title']='SINTETICO 9A SIN VALIDEZ INSTITUCIONAL'
        with path.open('xb') as f:pdf.save(f)


@unittest.skipUnless(os.environ.get('GEOLOGY_DOCUMENT_E2E')=='local-approved','Flujo documental sintÃƒÂ©tico explÃƒÂ­cito')
class DocumentalLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.environ['GEOLOGY_LOCAL_PROJECT']=='geology-local-20261106-57a99a'
        assert motor.url.host=='almacen_datos' and motor.url.database=='geology'
        assert HTTP_BASE in ('http://127.0.0.1:8080','http://servidor:8080')
        assert os.environ['LEVANTAR_AL_CARGAR'].lower() in ('no','false','0')
        assert all(not v for k,v in os.environ.items() if k.startswith(('GEMINI_API_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY')))
        assert 3<=PAGINAS_POR_PARTE<=500
        registrar_modelos();assert len(inspect(motor).get_table_names())==27
        resume=os.environ.get('GEOLOGY_E2E_RESUME')=='owned-fixture'
        cls.before=filas_previas();cls.run_id=secrets.token_hex(6)
        cls.old=secrets.token_urlsafe(36);cls.password=secrets.token_urlsafe(36)
        if resume:
            # Recuperación exclusiva del setup fallido antes de cualquier HTTP.
            dirs=list((ROOT/'deposito'/'pruebas_sinteticas').glob('fase9a-*'))
            assert len(dirs)==1
            cls.inputs=dirs[0];cls.run_id=cls.inputs.name.removeprefix('fase9a-')
            cls.small=cls.inputs/(CODIGOS[0]+'.pdf');cls.large=cls.inputs/(CODIGOS[1]+'.pdf')
            assert cls.small.is_file() and cls.large.is_file()
            with SesionLocal.begin() as s:
                assert s.query(Expediente).filter(Expediente.codigo_carpeta.in_(CODIGOS)).count()==0
                u=s.query(UsuarioBD).filter_by(correo=EMAIL).one()
                assert u.nombre=='ACTOR SINTETICO 9A' and u.rol=='equipo' and u.debe_cambiar_clave
                periodo=s.query(Periodo).filter_by(entidad_productora='PRODUCTOR SINTETICO 9A').one()
                sub=s.query(Subserie).filter_by(codigo='S91',nombre='SUBSERIE SINTETICA 9A').one()
                cls.periodo_id=periodo.id;cls.subserie_id=sub.id
                u.clave_hash=cifrar_clave(cls.old);u.intentos_fallidos=0
                assert clave_correcta(cls.old,u.clave_hash)
            # Excluir solo las filas propias creadas por el setup anterior.
            own={
                'cuenta':lambda x:x['correo']==EMAIL,
                'fondo_archivistico':lambda x:x['nombre']=='FONDO SINTETICO 9A',
                'periodo_institucional':lambda x:x['id']==cls.periodo_id,
                'seccion_documental':lambda x:x['periodo_id']==cls.periodo_id,
                'serie_documental':lambda x:x['nombre']=='SERIE SINTETICA 9A',
                'subserie_documental':lambda x:x['id']==cls.subserie_id,
                'inventario_origen':lambda x:x['codigo_carpeta'] in CODIGOS}
            cls.before={t:[x for x in rows if not own.get(t,lambda x:False)(x)] for t,rows in cls.before.items()}
        else:
            cls.inputs=ROOT/'deposito'/'pruebas_sinteticas'/('fase9a-'+cls.run_id)
            cls.inputs.mkdir(parents=True,exist_ok=False)
            cls.small=cls.inputs/(CODIGOS[0]+'.pdf');cls.large=cls.inputs/(CODIGOS[1]+'.pdf')
            crear_pdf(cls.small,3);crear_pdf(cls.large,PAGINAS_POR_PARTE+1)
            cuenta=CuentaNueva(nombre='ACTOR SINTETICO 9A',correo=EMAIL,rol='equipo',funcion='Ambas',clave=cls.old)
            rol,funcion=_validar_rol_y_funcion(cuenta.rol,cuenta.funcion)
            with SesionLocal.begin() as s:
                assert s.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta.in_(CODIGOS)).count()==0
                assert s.query(UsuarioBD).filter_by(correo=EMAIL).count()==0
                fondo=Fondo(nombre='FONDO SINTETICO 9A',historia_institucional='Fixture sin validez institucional')
                periodo=Periodo(numero_romano='IX',orden=900,fecha_inicio=date(2000,1,1),fecha_fin=date(2009,12,31),
                    entidad_productora='PRODUCTOR SINTETICO 9A',fondo=fondo)
                seccion=Seccion(periodo=periodo,codigo_dependencia='SYN9A',oficina_productora='OFICINA SINTETICA 9A')
                serie=Serie(seccion=seccion,codigo='S9',nombre='SERIE SINTETICA 9A')
                sub=Subserie(serie=serie,codigo='S91',nombre='SUBSERIE SINTETICA 9A',soporte='Papel sintético')
                usuario=UsuarioBD(nombre=cuenta.nombre,correo=EMAIL,rol=rol,funcion=funcion,
                    clave_hash=cifrar_clave(cls.old),activo=True,debe_cambiar_clave=True,intentos_fallidos=0)
                s.add_all([fondo,periodo,seccion,serie,sub,usuario]);s.flush()
                assert clave_correcta(cls.old,usuario.clave_hash) and _a_usuario(usuario).rol is Rol.EQUIPO
                cls.periodo_id=periodo.id;cls.subserie_id=sub.id
                for code,n in zip(CODIGOS,(3,PAGINAS_POR_PARTE+1)):
                    s.add(UnidadInventario(codigo_carpeta=code,periodo='IX',folios=n,asunto='SINTETICO 9A SIN VALIDEZ INSTITUCIONAL',
                        caja_origen='SYN9A',cod_serie='S9',serie=serie.nombre,cod_subserie='S91',subserie=sub.nombre))
        cls.token='';cls.events=[];cls.responses={};cls.splits=[]

    def api(self,path,method='GET',body=None,raw=None,content_type='application/json'):
        assert path.startswith(('/cuentas/','/unidades','/cargue/'))
        headers={'Content-Type':content_type}
        if self.token:headers['Authorization']='Bearer '+self.token
        payload=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(HTTP_BASE+path,data=payload,headers=headers,method=method)
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=45) as f:
                status=f.status;result=json.load(f)
        except urllib.error.HTTPError as e:status=e.code;result=json.load(e)
        self.events.append({'method':method,'path':path,'status':status})
        return status,result

    def upload(self,code,payload,reemplazar=False):
        boundary='SYN9A'+secrets.token_hex(12)
        chunks=[f'--{boundary}\r\nContent-Disposition: form-data; name="archivo"; filename="{code}.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode(),payload,
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="reemplazar"\r\n\r\n{str(reemplazar).lower()}\r\n--{boundary}--\r\n'.encode()]
        return self.api('/cargue/cargar','POST',raw=b''.join(chunks),content_type='multipart/form-data; boundary='+boundary)

    def test_01_autenticacion_real(self):
        status,r=self.api('/cuentas/ingresar','POST',{'correo':EMAIL,'clave':self.old});self.assertEqual(status,200)
        type(self).token=r['pase'];self.assertTrue(r['usuario']['debe_cambiar_clave'])
        self.assertEqual(self.api('/cuentas/cambiar-clave','POST',{'clave_actual':self.old,'clave_nueva':self.password})[0],200)
        self.assertEqual(self.api('/cuentas/yo')[0],200)

    def test_02_inventario_y_tvd_http(self):
        status,r=self.api('/unidades/inventario/'+CODIGOS[0]);self.assertEqual(status,200)
        self.assertEqual(r['codigo_carpeta'],CODIGOS[0])

    def test_03_cargue_pequeno(self):
        status,r=self.upload(CODIGOS[0],self.small.read_bytes());self.responses['small']=r
        self.assertEqual(status,200);self.assertFalse(r['levantamiento_automatico'])

    def test_04_cargue_y_division_real(self):
        status,r=self.upload(CODIGOS[1],self.large.read_bytes());self.responses['large']=r
        self.assertEqual(status,200);self.assertFalse(r['levantamiento_automatico'])
        with SesionLocal() as s:
            parts=s.query(Archivo).filter_by(codigo_carpeta=CODIGOS[1]).order_by(Archivo.fragmento).all()
            self.assertEqual(len(parts),2);self.assertEqual([a.paginas for a in parts],[PAGINAS_POR_PARTE,1])
            self.assertEqual([(a.pagina_inicial,a.pagina_final) for a in parts],[(1,PAGINAS_POR_PARTE),(PAGINAS_POR_PARTE+1,PAGINAS_POR_PARTE+1)])

    def test_05_original_y_hashes_sql(self):
        for code,source in zip(CODIGOS,(self.small,self.large)):
            with SesionLocal() as s:
                exp=s.query(Expediente).filter_by(codigo_carpeta=code).one()
                archivos=s.query(Archivo).filter_by(expediente_id=exp.id).all();self.assertTrue(archivos)
                for a in archivos:
                    self.assertTrue(Path(a.ruta).is_file());self.assertEqual(huella(a.ruta),a.sha256)
                    original=Path(a.ruta).parent/'original.pdf'
                    self.assertTrue(original.is_file());self.assertEqual(huella(original),huella(source))
                    if code==CODIGOS[1]:self.assertEqual(a.sha256_origen,huella(source))
                self.assertTrue(s.query(Trazabilidad).filter_by(expediente_id=exp.id).count())

    def test_06_reemplazo_corrupto_conserva_anterior(self):
        with SesionLocal() as s:
            antes=[(a.id,a.ruta,a.sha256) for a in s.query(Archivo).filter_by(codigo_carpeta=CODIGOS[0]).all()]
        self.assertTrue(antes)
        status,r=self.upload(CODIGOS[0],b'SINTETICO PDF CORRUPTO 9A',True)
        self.responses['failed_replacement_status']=status;self.assertEqual(status,422)
        with SesionLocal() as s:self.assertEqual([(a.id,a.ruta,a.sha256) for a in s.query(Archivo).filter_by(codigo_carpeta=CODIGOS[0]).all()],antes)
        for ident,path,sha in antes:self.assertEqual(huella(path),sha)

    def test_07_duplicado_rechazado(self):
        self.assertEqual(self.upload(CODIGOS[0],self.small.read_bytes())[0],409)

    def test_08_rollback_sql_controlado(self):
        with SesionLocal() as s:
            count=s.query(Tramite).count()
            with self.assertRaises(IntegrityError):
                s.add(Tramite(expediente_id=-987654321,no_item=1,tipo_documental='SINTETICO INVALIDO'));s.flush()
            s.rollback();self.assertEqual(s.query(Tramite).count(),count)

    def test_09_hoja_manual_y_clasificacion(self):
        with SesionLocal() as s:
            exp=s.query(Expediente).filter_by(codigo_carpeta=CODIGOS[0]).one()
            self.assertTrue(s.query(Archivo).filter_by(expediente_id=exp.id).count())
        self.assertEqual(self.api('/unidades/'+CODIGOS[0]+'/encuadernacion','POST',{'es_libro':False})[0],200)
        hoja={'codigo_carpeta':CODIGOS[0],'codigo_serie':'S9','serie':'SERIE SINTETICA 9A',
            'codigo_subserie':'S91','subserie':'SUBSERIE SINTETICA 9A','nombre_expediente':'EXPEDIENTE SINTETICO 9A',
            'fecha_diligenciamiento':'2026-11-07','modo':'verificar','tramites':[
                {'no_item':i,'fecha':f'2001-{i:02d}-01','tipo_documental':f'ACTA SINTETICA PAGINA {i}',
                 'folio_desde':i,'folio_hasta':i,'observaciones':'SINTETICO 9A'} for i in range(1,4)]}
        (self.inputs/'hoja_manual_sintetica.json').write_text(json.dumps(hoja,indent=2),encoding='utf-8')
        incompleta={**hoja,'codigo_subserie':'DESCONOCIDA_9A'}
        status,r=self.api('/unidades/hoja-de-control','POST',incompleta)
        self.assertEqual(status,200);self.assertTrue(r['errores'])
        self.assertEqual(r['estado'],Estado.HOJA_EN_ELABORACION.value)
        self.assertEqual(self.api('/unidades/'+CODIGOS[0]+'/marcar-revisada','POST')[0],409)
        status,r=self.api('/unidades/hoja-de-control','POST',hoja);self.responses['manual']=r
        self.assertEqual(status,200);self.assertEqual(r['errores'],[])
        self.assertEqual(r['estado'],Estado.HOJA_POR_REVISAR.value)
        with SesionLocal() as s:
            e=s.query(Expediente).filter_by(codigo_carpeta=CODIGOS[0]).one()
            self.assertEqual((e.periodo_id,e.subserie_id),(self.periodo_id,self.subserie_id))
            self.assertEqual((e.fecha_inicial,e.fecha_final),(date(2001,1,1),date(2001,3,1)))

    def test_10_paso_humano_explicito_sintetico(self):
        with SesionLocal() as s:
            e=s.query(Expediente).filter_by(codigo_carpeta=CODIGOS[0]).one()
            self.assertEqual(e.estado,Estado.HOJA_POR_REVISAR.value)
        status,r=self.api('/unidades/'+CODIGOS[0]+'/marcar-revisada','POST')
        self.assertEqual(status,200);self.assertEqual(r['estado'],Estado.HOJA_REVISADA.value)
        with SesionLocal() as s:
            e=s.query(Expediente).filter_by(codigo_carpeta=CODIGOS[0]).one()
            self.assertEqual(e.reviso_hoja,'ACTOR SINTETICO 9A');self.assertIsNone(e.aprobo)
            self.assertFalse(e.publicado_consulta)

    def test_11_consulta_y_trazabilidad_http(self):
        for path in ('/unidades/'+CODIGOS[0],'/unidades/'+CODIGOS[0]+'/trazabilidad'):
            self.assertEqual(self.api(path)[0],200)

    def test_12_tareas_tecnicas_sin_ia(self):
        limite=time.monotonic()+240
        while time.monotonic()<limite:
            with SesionLocal() as s:
                archivos=s.query(Archivo).filter(Archivo.codigo_carpeta.in_(CODIGOS)).all()
                if archivos and all(a.procesado_en or a.error_proceso for a in archivos):
                    summary=[{'id':a.id,'matriz':a.ruta_matriz,'consulta':a.ruta_consulta,'error':a.error_proceso} for a in archivos]
                    break
            time.sleep(2)
        else:self.fail('Timeout de tareas tÃƒÂ©cnicas sintÃƒÂ©ticas')
        self.responses['technical']=summary
        self.assertEqual(len(summary),3)
        for a in summary:
            self.assertFalse(a['error']);self.assertTrue(Path(a['matriz']).is_file());self.assertTrue(Path(a['consulta']).is_file())

    def test_13_registros_previos_intactos(self):
        actual=filas_previas()
        for table,rows in self.before.items():
            pk=[c.name for c in Base.metadata.tables[table].primary_key]
            for row in rows:
                found=[x for x in actual[table] if all(x[k]==row[k] for k in pk)]
                self.assertEqual(len(found),1);self.assertEqual(resumen_previas(found),resumen_previas([row]))

    def test_14_integridad_tras_reinicio_autorizado(self):
        if self._outcome.result.failures or self._outcome.result.errors:
            self.skipTest('Reinicio condicionado a resolver fallos previos')
        OUT.mkdir(parents=True,exist_ok=True)
        with SesionLocal() as s:
            filas=s.query(Archivo).filter(Archivo.codigo_carpeta.in_(CODIGOS)).all()
            hashes={a.ruta:huella(a.ruta) for a in filas}
        (OUT/'ready-for-restart.json').write_text(json.dumps({'run':self.run_id,'codes':CODIGOS}),encoding='utf-8')
        deadline=time.monotonic()+180
        while not (OUT/'restart-complete.json').exists():
            if time.monotonic()>deadline:self.fail('No llegÃ³ confirmaciÃ³n del reinicio controlado')
            time.sleep(1)
        for path,sha in hashes.items():self.assertEqual(huella(path),sha)
        status,result=self.api('/unidades/'+CODIGOS[0]);self.assertEqual(status,200)
        with SesionLocal() as s:
            e=s.query(Expediente).filter_by(codigo_carpeta=CODIGOS[0]).one()
            self.assertEqual(e.estado,Estado.HOJA_REVISADA.value)
            self.assertFalse(e.publicado_consulta);self.assertIsNone(e.aprobo)

    @classmethod
    def tearDownClass(cls):
        OUT.mkdir(parents=True,exist_ok=True)
        with SesionLocal() as s:
            exps=s.query(Expediente).filter(Expediente.codigo_carpeta.in_(CODIGOS)).all()
            data={'run':cls.run_id,'synthetic':True,'input_directory':str(cls.inputs),'codes':CODIGOS,
                'http_events':cls.events,'responses':cls.responses,'states':{e.codigo_carpeta:e.estado for e in exps},
                'source_hashes':{str(p):huella(p) for p in (cls.small,cls.large)}}
        (OUT/'evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        cls.old=cls.password=cls.token=None


if __name__=='__main__':unittest.main()
