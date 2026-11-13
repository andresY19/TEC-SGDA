"""Integración explícita, solo PostgreSQL GEOLOGY local. Fixtures propios negativos."""
import os,unittest,secrets
from sqlalchemy import text,inspect
from sqlalchemy.exc import IntegrityError,OperationalError
from geology.nucleo.bd import motor,Base,registrar_modelos
from geology.modelos import Caja
from sqlalchemy.orm import Session


@unittest.skipUnless(os.environ.get('GEOLOGY_INTEGRATION')=='local-approved','Integración local explícita')
class PostgreSQLLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.environ.get('GEOLOGY_LOCAL_PROJECT')=='geology-local-20261106-57a99a'
        assert motor.url.host=='almacen_datos' and motor.url.database=='geology'
        registrar_modelos()

    def test_01_conexion(self):
        with motor.connect() as c:
            self.assertEqual(c.execute(text('select current_database()')).scalar_one(),'geology')
            self.assertTrue(c.execute(text('show server_version')).scalar_one().startswith('15.'))

    def test_02_tablas_y_columnas(self):
        with motor.connect() as c:
            i=inspect(c);self.assertEqual(set(i.get_table_names(schema='public')),set(Base.metadata.tables))
            for name,t in Base.metadata.tables.items():
                self.assertEqual({x['name'] for x in i.get_columns(name)},set(t.columns.keys()))

    def test_03_claves_foraneas(self):
        with motor.connect() as c:
            i=inspect(c)
            for name,t in Base.metadata.tables.items():
                expected={(fk.parent.name,fk.column.table.name,fk.column.name) for fk in t.foreign_keys}
                actual={(col,f['referred_table'],ref) for f in i.get_foreign_keys(name)
                        for col,ref in zip(f['constrained_columns'],f['referred_columns'])}
                self.assertEqual(actual,expected)

    def test_04_indices_y_pk(self):
        with motor.connect() as c:
            i=inspect(c)
            for name,t in Base.metadata.tables.items():
                self.assertEqual(i.get_pk_constraint(name)['constrained_columns'],[x.name for x in t.primary_key])
                reflected={x['name'] for x in i.get_indexes(name)}
                self.assertTrue({x.name for x in t.indexes}<=reflected)

    def test_05_check_real_con_rollback(self):
        ident=-secrets.randbelow(1_000_000_000)-1
        with motor.connect() as c:
            outer=c.begin()
            try:
                nested=c.begin_nested()
                with self.assertRaises(IntegrityError):
                    c.execute(text("insert into caja(id,codigo,periodo,total_carpetas) values(:id,:cod,'SYNTH',-1)"),{'id':ident,'cod':f'TEST{abs(ident)}'})
                nested.rollback()
            finally:outer.rollback()

    def test_06_unicidad_y_rollback(self):
        ident=-secrets.randbelow(1_000_000_000)-1;code=f'TEST{abs(ident)}'
        with motor.connect() as c:
            outer=c.begin()
            try:
                c.execute(text("insert into caja(id,codigo,periodo) values(:id,:cod,'SYNTH')"),{'id':ident,'cod':code})
                nested=c.begin_nested()
                with self.assertRaises(IntegrityError):
                    c.execute(text("insert into caja(id,codigo,periodo) values(:id,:cod,'SYNTH')"),{'id':ident-1,'cod':code})
                nested.rollback()
            finally:outer.rollback()
        with motor.connect() as c:self.assertEqual(c.execute(text('select count(*) from caja where codigo=:c'),{'c':code}).scalar_one(),0)

    def test_07_persistencia_en_savepoint_reversible(self):
        ident=-secrets.randbelow(1_000_000_000)-1
        with motor.connect() as c:
            outer=c.begin()
            try:
                with Session(bind=c,join_transaction_mode='create_savepoint') as s:
                    s.add(Caja(id=ident,codigo=f'TEST{abs(ident)}',periodo='SYNTH'));s.commit()
                with Session(bind=c) as s:
                    fila=s.get(Caja,ident);self.assertIsNotNone(fila);self.assertFalse(fila.cerrada)
            finally:outer.rollback()
        with motor.connect() as c:self.assertEqual(c.execute(text('select count(*) from caja where id=:i'),{'i':ident}).scalar_one(),0)

    def test_08_bloqueo_real_fila_nowait(self):
        # Para observar un bloqueo desde dos conexiones la fixture debe ser visible.
        # Se confirma temporalmente y se borra SOLO esta fila propia identificada.
        ident=-secrets.randbelow(1_000_000_000)-1;code=f'TEST{abs(ident)}'
        with motor.begin() as c:c.execute(text("insert into caja(id,codigo,periodo) values(:i,:c,'SYNTH')"),{'i':ident,'c':code})
        try:
            with motor.connect() as a,motor.connect() as b:
                ta=a.begin();tb=b.begin()
                try:
                    a.execute(text('select id from caja where id=:i for update'),{'i':ident})
                    with self.assertRaises(OperationalError) as error:
                        b.execute(text('select id from caja where id=:i for update nowait'),{'i':ident})
                    self.assertEqual(error.exception.orig.pgcode,'55P03')
                finally:tb.rollback();ta.rollback()
        finally:
            with motor.begin() as c:
                removed=c.execute(text('delete from caja where id=:i and codigo=:c'),{'i':ident,'c':code})
                self.assertEqual(removed.rowcount,1)

    def test_09_transporte_redis_sin_worker(self):
        from geology.nucleo.cola import celery_app
        with celery_app.connection() as c:
            c.ensure_connection(max_retries=0)
            self.assertTrue(c.connected)

    def test_10_tipos_nulabilidad_unique_y_checks(self):
        from sqlalchemy import UniqueConstraint,CheckConstraint
        with motor.connect() as c:
            i=inspect(c)
            for name,t in Base.metadata.tables.items():
                actual={x['name']:x for x in i.get_columns(name)}
                for col in t.columns:
                    self.assertEqual(actual[col.name]['nullable'],col.nullable)
                    self.assertEqual(actual[col.name]['type']._type_affinity,col.type._type_affinity)
                unique={tuple(x['column_names']) for x in i.get_unique_constraints(name)}
                self.assertEqual(unique,{tuple(x.columns.keys()) for x in t.constraints if isinstance(x,UniqueConstraint)})
                self.assertEqual(len(i.get_check_constraints(name)),sum(isinstance(x,CheckConstraint) for x in t.constraints))


if __name__=='__main__':unittest.main()
