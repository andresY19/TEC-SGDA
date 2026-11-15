"""Especificación local preparada antes de implementar; solo datos sintéticos."""
import copy
from datetime import date, datetime
import io
import unittest
import os,secrets,tempfile,json,zipfile,ast
from types import SimpleNamespace as Obj
from contextlib import nullcontext
from unittest.mock import Mock, patch


class DominioCompleto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ,{'DATABASE_URL':'postgresql+psycopg2://synthetic:synthetic@db.invalid:5432/synthetic'},clear=True)
        cls.env.start()
    @classmethod
    def tearDownClass(cls): cls.env.stop()

    def libro(self,modificar=None,segunda=False):
        from openpyxl import Workbook
        from geology.dominio import formatos_sgc as f
        w=Workbook();h=w.active;h.title='AC-CP-00001'
        h['A1']='F-GDM-007 versión 4'
        for k,celda in f.HC_ENCABEZADO.items(): h[celda]=k
        valores={'no_item':1,'tipo_documental':'Acta sintética','fecha':'1901-01-01',
                 'folio_desde':1,'folio_hasta':2}
        for k,col in f.HC_COLUMNAS.items():h[f'{col}11']=valores.get(k,'')
        h['D33']='2026-01-01'
        if segunda:w.copy_worksheet(h).title='AC-CP-00002'
        if modificar:modificar(w,h)
        b=io.BytesIO();w.save(b);w.close();return b.getvalue()

    def test_excel_valido(self):
        from geology.dominio.importar_hoja import leer_libro
        h=leer_libro(self.libro())[0]
        self.assertEqual(h.codigo_carpeta,'AC-CP-00001');self.assertEqual(len(h.tramites),1)
        self.assertEqual(h.tramites[0]['fila'],11)

    def test_excel_varias_hojas_lectura_completa(self):
        from geology.dominio.importar_hoja import leer_libro
        self.assertEqual(len(leer_libro(self.libro(segunda=True))),2)

    def test_excel_segunda_mala_rechaza_todo(self):
        from geology.dominio.importar_hoja import leer_libro
        raw=self.libro(lambda w,h:setattr(w.worksheets[1]['A1'],'value','desconocido'),True)
        with self.assertRaises(ValueError):leer_libro(raw)

    def test_excel_formulas_rechazadas(self):
        from geology.dominio.importar_hoja import leer_libro
        for valor in ('=1+1','+cmd','@SUM(1)'):
            raw=self.libro(lambda w,h:setattr(h['E11'],'value',valor))
            with self.assertRaises(ValueError):leer_libro(raw)

    def test_excel_folios_invalidos(self):
        from geology.dominio.importar_hoja import leer_libro
        for valor in (-1,'ilegible',0):
            with self.assertRaises(ValueError):leer_libro(self.libro(lambda w,h:setattr(h['G11'],'value',valor)))

    def test_excel_fecha_invalida(self):
        from geology.dominio.importar_hoja import leer_libro
        with self.assertRaises(ValueError):leer_libro(self.libro(lambda w,h:setattr(h['D11'],'value','no fecha')))

    def test_excel_version_desconocida(self):
        from geology.dominio.importar_hoja import leer_libro
        with self.assertRaises(ValueError):leer_libro(self.libro(lambda w,h:setattr(h['A1'],'value','F-GDM-007 versión 40')))

    def test_excel_diligenciamiento_invalido(self):
        from geology.dominio.importar_hoja import leer_libro
        with self.assertRaises(ValueError):leer_libro(self.libro(lambda w,h:setattr(h['D33'],'value','1901-01-01')))

    def test_excel_fecha_parcial_no_inventada(self):
        from geology.dominio.importar_hoja import leer_libro
        self.assertEqual(leer_libro(self.libro(lambda w,h:setattr(h['D11'],'value','1901')))[0].tramites[0]['fecha'],'1901')

    def test_excel_codigo_numerico_rechazado(self):
        from geology.dominio.importar_hoja import leer_libro
        with self.assertRaises(ValueError):leer_libro(self.libro(lambda w,h:setattr(h['I6'],'value',1)))

    def test_excel_fila_oculta_no_se_salta(self):
        from geology.dominio.importar_hoja import leer_libro
        def cambiar(w,h): h['B13']=2;h['E13']='Acta';h['G13']=3;h['H13']=4
        with self.assertRaises(ValueError):leer_libro(self.libro(cambiar))

    def test_excel_codigo_carpeta_desconocido(self):
        from geology.dominio.importar_hoja import leer_libro
        with self.assertRaises(ValueError):leer_libro(self.libro(lambda w,h:setattr(h,'title','sin_codigo')))

    def test_excel_macros_rechazadas(self):
        from geology.dominio.importar_hoja import leer_libro
        b=io.BytesIO(self.libro())
        with zipfile.ZipFile(b,'a') as z:z.writestr('xl/vbaProject.bin',b'macro sintetica')
        with self.assertRaises(ValueError):leer_libro(b.getvalue())

    def test_libros_extremos_ausentes(self):
        from geology.dominio.libros import resolver_fechas
        self.assertIsNone(resolver_fechas([Obj(fecha=None),Obj(fecha=date(1901,1,1))],None,True)[0])

    def test_libros_contradiccion_periodo(self):
        from geology.dominio.libros import resolver_fechas
        r=resolver_fechas([Obj(fecha=date(1901,1,1))],None,False,date(1910,1,1),date(1920,1,1))
        self.assertIsNone(r[0]);self.assertTrue(r[4])

    def test_libros_fecha_parcial(self):
        from geology.dominio.libros import resolver_fechas
        r=resolver_fechas([Obj(fecha=None,fecha_texto='1901')],None,False)
        self.assertIsNone(r[0]);self.assertTrue(r[4])

    def test_revision_propuestas_bloquean(self):
        from geology.dominio import revision_isadg as rv
        from geology.dominio.base_isadg import Renglon
        r=Renglon('Unidad documental',{'titulo':'[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] Título'})
        h=rv.revisar([r],{});self.assertTrue(any(x.regla=='PROPUESTA_PENDIENTE' for x in h))
        self.assertFalse(rv.resumen(h)['se_puede_entregar'])

    def test_revision_fechas_invertidas(self):
        from geology.dominio import revision_isadg as rv
        from geology.dominio.base_isadg import Renglon
        h=rv.revisar([Renglon('Unidad documental',{'fecha_inicial':'1902-01-01','fecha_final':'1901-01-01'})],{})
        self.assertTrue(any(x.regla=='FECHAS_INVERTIDAS' for x in h))

    def test_revision_datos_completos_siguen_pendientes(self):
        from geology.dominio import revision_isadg as rv
        from geology.dominio.base_isadg import Renglon
        h=rv.revisar([Renglon('Unidad documental',dict(codigo_referencia='X',titulo='Título',volumen='2 folios',norma='ISAD(G)'))],{})
        self.assertTrue(any(x.gravedad==rv.REVISE for x in h));self.assertFalse(rv.resumen(h)['se_puede_entregar'])

    def test_revisor_no_consulta_db_ni_red(self):
        from geology.dominio.revisor import revisar_lote
        with patch('socket.socket.connect',side_effect=AssertionError):
            h,r=revisar_lote(Mock(),[Obj()],{},limite=1)
        self.assertTrue(r['revision_pendiente']);self.assertEqual(r['revisados'],0)

    def test_lector_revision_directa_desactivado(self):
        from geology.dominio import lectores
        with patch.object(lectores,'_intentar',side_effect=AssertionError):
            self.assertIsNone(lectores.revisar_descripcion(Mock(),'Instrucción sintética'))

    def test_expedir_rechaza_no_revisada(self):
        from geology.dominio.expedir import datos_de_hoja
        db=Mock();db.no_autoflush=nullcontext()
        with self.assertRaises(ValueError):datos_de_hoja(db,Obj(estado='En cola'))

    def test_expedir_rechaza_tvd_incompleta(self):
        from geology.dominio.expedir import datos_de_hoja
        db=Mock();db.no_autoflush=nullcontext()
        e=Obj(estado='Hoja de control revisada',reviso_hoja='Persona',fecha_revision=date(2026,1,1),
            tramites=[],subserie_id=None,periodo_id=1)
        with self.assertRaises(ValueError):datos_de_hoja(db,e)
        db.commit.assert_not_called()

    def test_expedir_contrato_real_sin_mutar_y_con_firma_existente(self):
        from geology.dominio.expedir import datos_de_hoja
        db=Mock();db.no_autoflush=nullcontext()
        objetos={'Subserie':Obj(serie_id=2,codigo='003',nombre='Subserie'),
            'Serie':Obj(seccion_id=3,codigo='002',nombre='Serie'),
            'Seccion':Obj(periodo_id=1,codigo_dependencia='001',oficina_productora='Oficina')}
        db.get.side_effect=lambda cls,identificador:objetos[cls.__name__]
        e=Obj(estado='Hoja de control revisada',reviso_hoja='Persona real del registro sintético',fecha_revision=date(2026,1,1),
            tramites=[Obj(tipo_documental='Acta',observaciones='Sin novedad',fecha=None,fecha_texto='S/F')],subserie_id=4,periodo_id=1,
            nombre_expediente='Campo 7',responsable_hoja='Elaboró',fecha_diligenciamiento=date(2026,1,1))
        datos=datos_de_hoja(db,e)
        self.assertEqual(datos['nombre_expediente'],'Campo 7');self.assertEqual(datos['reviso_hoja'],e.reviso_hoja)
        self.assertEqual(datos['codigo_dependencia'],'001');db.commit.assert_not_called()
        self.assertEqual(datos['tramites'][0]['fecha'],'S/F')

    def test_calidad_exportacion_formula_literal(self):
        from geology.dominio.control_calidad import Informe,Hallazgo,informe_a_excel,REVISAR
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as d:
            p=informe_a_excel(Informe(1,[Hallazgo('AC-CP-00001',REVISAR,'P','=1+1')]),destino=d)
            w=load_workbook(p);self.assertEqual(w.active['D2'].data_type,'s');w.close()

    def test_calidad_exportacion_no_sobrescribe(self):
        from geology.dominio.control_calidad import Informe,informe_a_excel
        with tempfile.TemporaryDirectory() as d:
            a=informe_a_excel(Informe(0,[]),destino=d);antes=a.read_bytes()
            b=informe_a_excel(Informe(0,[]),destino=d)
            self.assertNotEqual(a,b);self.assertEqual(a.read_bytes(),antes)

    def test_disposicion_completa_no_aprueba(self):
        from geology.dominio.disposicion import evaluar
        r=evaluar(Obj(codigo_carpeta='AC-CP-00001'),Obj(disposicion_final='E',retencion_central_anios=5),Obj(fecha_convalidacion_tvd=date(2000,1,1)))
        self.assertFalse(r['elegible']);self.assertTrue(r['requiere_persona'])

    def test_eventos_sin_usuario_no_inventan_persona(self):
        from geology.dominio.produccion import resumir_eventos
        r=resumir_eventos([Obj(fecha=datetime(2026,1,1),accion='verificar',usuario=None)],date(2026,1,1))
        self.assertEqual(r['total'],1);self.assertEqual(r['hoy_por_persona'][0]['persona'],'Sin usuario registrado')

    def test_eventos_otros_dias_acciones_no_productivas(self):
        from geology.dominio.produccion import resumir_eventos
        filas=[Obj(fecha=datetime(2025,1,1),accion='verificar',usuario='Persona'),Obj(fecha=datetime(2026,1,1),accion='ingresar',usuario='Persona')]
        self.assertEqual(resumir_eventos(filas,date(2026,1,1))['total'],0)

    def test_eventos_repetidos_no_se_presentan_como_unidades(self):
        from geology.dominio.produccion import resumir_eventos
        e=Obj(fecha=datetime(2026,1,1),accion='verificar',usuario='Persona')
        r=resumir_eventos([e,e],date(2026,1,1));self.assertEqual(r['total'],2)
        self.assertIn('no unidades únicas',r['alcance'])

    def test_consumidor_excel_valida_antes_de_guardar(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        s=(root/'geology/rutas/cargue.py').read_text(encoding='utf-8')
        f=s[s.index('async def importar_hoja('):s.index('_IMAGENES =')]
        guardar = f.index('r = guardar_hoja(')
        self.assertLess(f.index('if not hojas or any('), guardar)
        self.assertLess(f.index('cuerpos = ['), guardar)
        self.assertLess(f.index('confirmar=False'), f.index('db.commit()'))
        self.assertIn('db.rollback()', f)
        self.assertNotIn('destino.open("wb")',f)

    def test_arranque_no_ejecutado_y_ddl_detectado(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        s=(root/'geology/main.py').read_text(encoding='utf-8')
        self.assertNotIn('for linea in aplicar()',s)
        self.assertNotIn('crear_tablas()',s)

    def test_clasificar_pendiente_no_cambia_expediente(self):
        from pathlib import Path
        import __future__
        r=Path(__file__).resolve().parents[1]
        tree=ast.parse((r/'geology/trabajos/__init__.py').read_text(encoding='utf-8-sig'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_clasificar')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'consumidor_real','exec',flags=__future__.annotations.compiler_flag),ns)
        exp=Obj(tramites=[Obj(fecha=date(1901,1,1))],encuadernada=None,
            fecha_inicial=date(1900,1,1),fecha_final=date(1902,1,1),periodo_id=9,subserie_id=8)
        antes=copy.deepcopy(vars(exp));db=Mock()
        avisos=ns['_clasificar'](db,exp,None)
        self.assertEqual(exp.periodo_id,antes['periodo_id']);self.assertEqual(exp.fecha_inicial,antes['fecha_inicial'])
        self.assertTrue(avisos[0]);self.assertEqual(db.mock_calls,[])

    def test_embudo_datos_reales_en_memoria(self):
        from geology.dominio.produccion import _embudo
        from geology.modelos import Expediente,UnidadInventario
        db=Mock();db.no_autoflush=nullcontext()
        e=Obj(estado='Archivado',tramites=[Obj()],titulo='Título',fecha_descripcion=date(2026,1,1),
            caja_definitiva='AH-CJ-00001',volumen_folios=2)
        q=Mock();q.count.return_value=1;q.all.return_value=[e];db.query.return_value=q
        u,emb=_embudo(db)
        self.assertEqual(u,1);self.assertEqual(emb['archivadas'],1);self.assertEqual(emb['folios_registrados'],2)
        db.commit.assert_not_called();db.flush.assert_not_called()

    def test_disposicion_consumer_no_inserta_candidatas(self):
        from geology.dominio.disposicion import revisar_todo
        db=Mock();db.no_autoflush=nullcontext()
        db.query.return_value.all.return_value=[Obj(codigo_carpeta='AC-CP-00001',subserie_id=None,periodo_id=None)]
        candidatas,resumen=revisar_todo(db)
        self.assertEqual(candidatas,[]);self.assertEqual(resumen['revisados'],1)
        db.add.assert_not_called();db.commit.assert_not_called()

    def test_calidad_lectura_sin_reparar(self):
        from geology.dominio.control_calidad import revisar_todo
        db=Mock();db.no_autoflush=nullcontext()
        e=Obj(codigo_carpeta='AC-CP-00001',fecha_inicial=None,fecha_final=None,periodo_id=None,subserie_id=None,tramites=[])
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value=[e]
        antes=copy.deepcopy(vars(e));informe=revisar_todo(db)
        self.assertEqual(informe.revisados,1);self.assertEqual(vars(e),antes);db.commit.assert_not_called()

    def test_calidad_reutiliza_obligatorios_existentes(self):
        from geology.dominio.control_calidad import revisar_unidad,ERROR
        e=Obj(codigo_carpeta='AC-CP-00001',fecha_inicial=None,fecha_final=None,
            periodo_id=1,subserie_id=1,tramites=[],estado='Descripción validada')
        self.assertTrue(any(h.gravedad==ERROR and h.prueba.startswith('ISADG_') for h in revisar_unidad(e)))
    def test_libros_orden_no_se_reordena(self):
        from geology.dominio.libros import resolver_fechas
        tramites=[Obj(fecha=date(1902,1,1)),Obj(fecha=date(1901,1,1))]
        antes=copy.deepcopy(tramites)
        a,b,texto,enc,avisos=resolver_fechas(tramites,None,True)
        self.assertIsNone(a); self.assertIsNone(b); self.assertTrue(avisos)
        self.assertEqual(tramites[0].fecha,antes[0].fecha)

    def test_libros_sueltos_extremas(self):
        from geology.dominio.libros import resolver_fechas
        a,b,*_=resolver_fechas([Obj(fecha=date(1902,1,1)),Obj(fecha=date(1901,1,1))],None,False)
        self.assertEqual((a,b),(date(1901,1,1),date(1902,1,1)))

    def test_libros_desconocido_no_infiere_por_asunto(self):
        from geology.dominio.libros import resolver_fechas
        a,b,_,enc,avisos=resolver_fechas([Obj(fecha=date(1901,1,1))],Obj(asunto='LIBRO'),None)
        self.assertIsNone(a); self.assertIsNone(enc); self.assertTrue(avisos)

    def test_excel_corrupto_rechazado(self):
        from geology.dominio.importar_hoja import leer_libro
        with self.assertRaises(ValueError): leer_libro(b'corrupto','AC-CP-00001.xlsx')

    def test_revision_vacia_no_aprueba(self):
        from geology.dominio import revision_isadg as rv
        self.assertFalse(rv.resumen(rv.revisar([],{}))['se_puede_entregar'])

    def test_revisor_siempre_deshabilitado(self):
        from geology.dominio.revisor import revisar_lote
        db=Mock()
        hallazgos,resumen=revisar_lote(db,[],{})
        self.assertEqual(resumen['revisados'],0); self.assertTrue(resumen['deshabilitado'])
        self.assertTrue(hallazgos); self.assertEqual(db.mock_calls,[])

    def test_revisores_historicos_no_se_completan(self):
        from geology.dominio.expedir import completar_revisores
        db=Mock(); self.assertEqual(completar_revisores(db),0)
        self.assertEqual(db.mock_calls,[])

    def test_disposicion_incompleta_no_propone(self):
        from geology.dominio.disposicion import evaluar
        r=evaluar(Obj(codigo_carpeta='AC-CP-00001',valoracion='Eliminar',subserie_id=None))
        self.assertFalse(r['elegible']); self.assertTrue(r['pendientes'])

    def test_calidad_contradiccion_fechas(self):
        from geology.dominio.control_calidad import revisar_unidad,ERROR
        e=Obj(codigo_carpeta='AC-CP-00001',fecha_inicial=date(1902,1,1),fecha_final=date(1901,1,1),
              periodo_id=None,subserie_id=None,tramites=[],estado='En cola')
        self.assertTrue(any(h.gravedad==ERROR for h in revisar_unidad(e)))

    def test_produccion_no_inventa_metas(self):
        from geology.dominio.produccion import resumir_eventos
        r=resumir_eventos([],date(2026,1,1))
        self.assertEqual(r['total'],0); self.assertNotIn('meta',r)


if __name__=='__main__': unittest.main()
