"""Pruebas ORM sin base de datos, en intérprete separado y con guardias de red/DDL."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from test_persistencia_contratos import SONDEO

ROOT = Path(__file__).resolve().parents[1]
EXTRA = r'''
    import ast, __future__
    from datetime import date, datetime
    from sqlalchemy import inspect, select, CheckConstraint, UniqueConstraint
    from sqlalchemy.orm import Session
    from geology.modelos import Fondo, Periodo, Seccion, Serie, Subserie, Trazabilidad, ConsumoModelo, Caja, Expediente
    f = Fondo(nombre='Fondo sintético', historia_institucional='Prueba')
    p = Periodo(numero_romano='II', fecha_inicio=date(1900,1,1), fecha_fin=date(1910,12,31), fondo=f)
    se = Seccion(periodo=p, codigo_dependencia='001', oficina_productora='Oficina')
    sr = Serie(seccion=se, codigo='002', nombre='Serie')
    su = Subserie(serie=sr, codigo='003', nombre='Subserie')
    e = Expediente(codigo_carpeta='A00001', estado='en_cola', periodo_id=1, subserie_id=1)
    t = Trazabilidad(expediente=e, estado_anterior=None, estado_nuevo='en_cola', accion='cargue',
                    usuario=None, errores='["sintético"]')
    c = Caja(codigo='001', periodo='II')
    consumo = ConsumoModelo(fecha=date(2026,1,1), proveedor='sintetico/modelo', peticiones=0)
    result['hierarchy'] = [p in f.periodos, se in p.secciones, sr in se.series, su in sr.subseries]
    result['trace_link'] = t in e.trazabilidad and t.expediente is e
    result['trace_by_id'] = Trazabilidad(expediente_id=7, estado_nuevo='en_cola', accion='cargue').expediente_id
    result['range_cases'] = [p.rango_texto, Periodo(numero_romano='X').rango_texto,
        Periodo(numero_romano='I', fecha_inicio=date(1900,1,1)).rango_texto,
        Periodo(numero_romano='I', fecha_inicio=date(1900,1,1), fecha_fin=date(1900,12,31)).rango_texto]
    result['defaults'] = {}
    for cls, names in ((Caja, ('total_carpetas','cerrada')), (Periodo, ('orden',)),
                       (ConsumoModelo, ('peticiones',)), (Trazabilidad, ('fecha',))):
        for name in names:
            col = cls.__table__.c[name]
            default = col.default.arg
            value = default(None) if callable(default) else default
            result['defaults'][cls.__name__+'.'+name] = value.isoformat() if isinstance(value,datetime) else value
    result['transient_defaults'] = [c.total_carpetas, c.cerrada]  # SQLAlchemy aplica defaults al INSERT, no al constructor.
    result['serialization'] = json.loads(json.dumps({'fecha':consumo.fecha.isoformat(),
        'proveedor':consumo.proveedor, 'peticiones':consumo.peticiones,
        'errores':json.loads(t.errores), 'caja':c.codigo, 'periodo':p.numero_romano},ensure_ascii=False))
    result['new_classes'] = {cls.__name__:cls.__tablename__ for cls in
        (Fondo,Periodo,Seccion,Serie,Subserie,Trazabilidad,ConsumoModelo,Caja)}
    result['relationship_pairs'] = {cls.__name__:{rel.key:rel.back_populates for rel in inspect(cls).relationships}
        for cls in (Fondo,Periodo,Seccion,Serie,Subserie,Trazabilidad)}
    result['new_delete_cascades'] = [cls.__name__+'.'+rel.key for cls in (Fondo,Periodo,Seccion,Serie,Subserie,Trazabilidad)
        for rel in inspect(cls).relationships if rel.cascade.delete or rel.cascade.delete_orphan]
    result['existing_orphan_risk'] = inspect(Expediente).relationships.trazabilidad.cascade.delete_orphan
    result['trace_fk_ondelete'] = next(iter(Trazabilidad.__table__.c.expediente_id.foreign_keys)).ondelete
    result['caja_fk'] = len(Caja.__table__.foreign_keys)
    result['fondo_nullable'] = Periodo.__table__.c.fondo_id.nullable
    result['checks'] = {cls.__name__:[str(con.sqltext) for con in cls.__table__.constraints
         if isinstance(con,CheckConstraint)] for cls in (ConsumoModelo,Caja)}
    result['caja_unique'] = any(isinstance(con,UniqueConstraint) and list(con.columns.keys())==['codigo']
        for con in Caja.__table__.constraints)
    result['codigo_not_global_unique'] = all(not cls.__table__.c.codigo.unique for cls in (Serie,Subserie))
    result['server_defaults'] = {cls.__name__+'.'+name:str(cls.__table__.c[name].server_default.arg)
        for cls,name in ((Caja,'cerrada'),(Caja,'total_carpetas'),(ConsumoModelo,'peticiones'),(Trazabilidad,'fecha'))}
    db = Session()  # Sin bind ni ejecución.
    ns = dict(db=db, Periodo=Periodo, Serie=Serie, Subserie=Subserie, Seccion=Seccion, romano='ii')
    tree = ast.parse(Path('geology/rutas/unidades.py').read_text(encoding='utf-8-sig'))
    fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_opciones_tvd')
    assignment = next(n for n in fn.body if isinstance(n,ast.Assign) and n.targets[0].id=='consulta')
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),'consumidor_real','exec'),ns)
    queries = {'tvd':ns['consulta'].statement,
        'clasificacion':select(Subserie).join(Serie,Subserie.serie_id==Serie.id).join(Seccion,Serie.seccion_id==Seccion.id)
            .join(Periodo,Seccion.periodo_id==Periodo.id).where(Periodo.numero_romano=='II', Serie.codigo=='002', Subserie.codigo=='003'),
        'consumo':db.query(ConsumoModelo).filter_by(fecha=date(2026,1,1),proveedor='sintetico/modelo').statement,
        'traza':select(Trazabilidad).where(Trazabilidad.expediente_id==7).order_by(Trazabilidad.fecha.desc(),Trazabilidad.id.desc()),
        'caja':select(Caja).where(Caja.codigo=='001',Caja.cerrada==False)}
    result['queries'] = {name:str(query.compile(dialect=dialect())) for name,query in queries.items()}
    # Ejecuta el constructor del consumidor real con un repositorio solo en memoria.
    tree = ast.parse(Path('geology/dominio/lectores.py').read_text(encoding='utf-8-sig'))
    fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_registro')
    ns = dict(date=date)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'registro_real','exec',flags=__future__.annotations.compiler_flag),ns)
    class Repositorio:
        def query(self,*args): return self
        def filter_by(self,**kw): self.filters=kw; return self
        def first(self): return None
        def add(self,obj): self.added=obj
        def flush(self): self.flushed=True
    repo=Repositorio()
    nuevo=ns['_registro'](repo,'sintetico/modelo')
    result['registro_consumer'] = [isinstance(nuevo,ConsumoModelo), nuevo.peticiones==0, repo.flushed,
                                 repo.added is nuevo, nuevo.fecha==date.today()]
    db.close()
    result['effects_after_construction'] = sum(g.call_count for g in guards)
'''


class ORMLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = SONDEO.replace("    bd.motor.dispose()", EXTRA + "\n    bd.motor.dispose()")
        proc = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT,
                              capture_output=True, text=True, timeout=40)
        if proc.returncode:
            raise AssertionError(proc.stderr)
        cls.data = json.loads(proc.stdout)

    def test_01_ocho_entidades(self):
        self.assertEqual(len(self.data['new_classes']), 8)

    def test_02_nombres_confirmados(self):
        self.assertEqual({n:self.data['new_classes'][n] for n in ('Periodo','Subserie','ConsumoModelo')},
                         {'Periodo':'periodo_institucional','Subserie':'subserie_documental','ConsumoModelo':'consumo_lector'})

    def test_03_nombres_propuestos(self):
        self.assertEqual({n:self.data['new_classes'][n] for n in ('Fondo','Seccion','Serie','Trazabilidad','Caja')},
            {'Fondo':'fondo_archivistico','Seccion':'seccion_documental','Serie':'serie_documental',
             'Trazabilidad':'trazabilidad','Caja':'caja'})

    def test_04_jerarquia_bidireccional(self):
        self.assertEqual(self.data['hierarchy'], [True]*4)

    def test_05_traza_por_objeto_y_id(self):
        self.assertTrue(self.data['trace_link'])
        self.assertEqual(self.data['trace_by_id'], 7)

    def test_06_rango_derivado(self):
        self.assertEqual(self.data['range_cases'], ['1900–1910','S/F','1900–S/F','1900'])

    def test_07_defaults_declarados(self):
        for key,value in (('Caja.total_carpetas',0),('Caja.cerrada',False),('Periodo.orden',0),('ConsumoModelo.peticiones',0)):
            self.assertEqual(self.data['defaults'][key],value)
        self.assertIn('T',self.data['defaults']['Trazabilidad.fecha'])
        self.assertEqual(self.data['transient_defaults'], [None,None])

    def test_08_defaults_de_servidor(self):
        self.assertEqual(self.data['server_defaults'], {'Caja.cerrada':'false','Caja.total_carpetas':'0',
            'ConsumoModelo.peticiones':'0','Trazabilidad.fecha':'now()'})

    def test_09_serializacion(self):
        self.assertEqual(self.data['serialization'], {'fecha':'2026-01-01','proveedor':'sintetico/modelo',
            'peticiones':0,'errores':['sintético'],'caja':'001','periodo':'II'})

    def test_10_consumo_pk_compuesta(self):
        self.assertEqual(self.data['tables']['consumo_lector']['pk'], ['fecha','proveedor'])

    def test_11_checks_de_contadores(self):
        self.assertEqual(self.data['checks'], {'ConsumoModelo':['peticiones >= 0'],'Caja':['total_carpetas >= 0']})

    def test_12_codigo_caja_unico_sin_fk(self):
        self.assertTrue(self.data['caja_unique'])
        self.assertEqual(self.data['caja_fk'],0)

    def test_13_sin_unicidad_global_de_series(self):
        self.assertTrue(self.data['codigo_not_global_unique'])
        self.assertTrue(self.data['fondo_nullable'])

    def test_14_no_agrega_borrado_historico(self):
        self.assertEqual(self.data['new_delete_cascades'],[])
        self.assertIsNone(self.data['trace_fk_ondelete'])
        self.assertTrue(self.data['existing_orphan_risk'])

    def test_15_consulta_tvd_real_compila(self):
        sql=self.data['queries']['tvd']
        for name in ('subserie_documental','serie_documental','seccion_documental','periodo_institucional'):
            self.assertIn(name,sql)
        self.assertEqual(sql.count(' JOIN '),3)

    def test_16_consultas_de_consumidores(self):
        self.assertIn('consumo_lector.proveedor =',self.data['queries']['consumo'])
        self.assertIn('trazabilidad.fecha DESC, trazabilidad.id DESC',self.data['queries']['traza'])
        self.assertIn('caja.codigo =',self.data['queries']['caja'])
        self.assertIn('serie_documental.codigo =',self.data['queries']['clasificacion'])

    def test_17_constructor_real_de_lectores(self):
        self.assertEqual(self.data['registro_consumer'],[True]*5)

    def test_18_back_populates(self):
        self.assertEqual(self.data['relationship_pairs']['Trazabilidad'],{'expediente':'trazabilidad'})
        self.assertEqual(self.data['relationship_pairs']['Periodo'],{'fondo':'periodos','secciones':'periodo'})

    def test_19_ddl_y_fk_completos(self):
        self.assertEqual(len(self.data['compiled']),27)
        self.assertEqual(self.data['unresolved_fk'],[])
        self.assertIsNone(self.data['mapping_error'])

    def test_20_sin_efectos_secundarios(self):
        self.assertEqual(self.data['effects_after_construction'],0)


if __name__ == '__main__':
    unittest.main()
