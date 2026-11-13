"""Contratos de persistencia actualizados para el ORM local 6B; sin DDL real.

Las pruebas de bloqueo de 6A pasan a comprobar la resolución de los contratos.
El sondeo usa los modelos reales en un intérprete independiente para no contaminar
el registro de las otras suites. Ejecutar en el contenedor sin red ni .env.
"""
import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODELOS = ROOT / "geology" / "modelos"
PENDIENTES = ("valoracion", "bitacora", "consumo_lector", "caja")


def arbol(nombre):
    return ast.parse((ROOT / nombre).read_text(encoding="utf-8-sig"))


# Importación normal del paquete completo, sin alias ni modelos sustitutos.
SONDEO = r'''
import contextlib, importlib.util, json, os, socket, sys
from pathlib import Path
from unittest.mock import patch
os.environ.clear()
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://synthetic:synthetic@db.invalid:5432/synthetic'
with contextlib.ExitStack() as stack:
    guards = [stack.enter_context(patch(target, side_effect=AssertionError('Efecto prohibido')))
              for target in ('socket.socket.connect', 'socket.create_connection',
                  'psycopg2.connect', 'sqlalchemy.engine.Engine.connect',
                  'sqlalchemy.sql.schema.MetaData.create_all',
                  'sqlalchemy.sql.schema.MetaData.drop_all')]
    from geology.nucleo import bd
    from sqlalchemy.orm import configure_mappers
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects.postgresql import dialect
    import geology.modelos
    tables = bd.Base.metadata.tables
    result = {'tables': {}, 'unresolved_fk': [], 'compiled': [], 'compile_errors': {}, 'mapping_error': None, 'blocked_modules': []}
    for name, table in tables.items():
        result['tables'][name] = {'columns': {
            c.name: {'type': str(c.type), 'nullable': c.nullable,
                     'pk': c.primary_key, 'unique': bool(c.unique)} for c in table.columns},
            'pk': [c.name for c in table.primary_key]}
        for fk in table.foreign_keys:
            try:
                fk.column
            except Exception as exc:
                result['unresolved_fk'].append([name, fk.parent.name, fk.target_fullname, type(exc).__name__])
        try:
            str(CreateTable(table).compile(dialect=dialect()))
            result['compiled'].append(name)
        except Exception as exc:
            result['compile_errors'][name] = type(exc).__name__
    result['mapped_class_count'] = len(list(bd.Base.registry.mappers))
    try:
        configure_mappers()
    except Exception as exc:
        result['mapping_error'] = type(exc).__name__
        result['missing_trazabilidad'] = 'Trazabilidad' in str(exc)
    try:
        bd.registrar_modelos()
    except RuntimeError as exc:
        result['blocked_modules'] = [name for name in
            ('valoracion', 'bitacora', 'consumo_lector', 'caja') if name in str(exc)]
    result['effects'] = sum(g.call_count for g in guards)
    result['full_package_imported'] = 'geology.modelos' in sys.modules
    bd.motor.dispose()
print(json.dumps(result))
'''


class PersistenciaContratos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([sys.executable, "-B", "-c", SONDEO], cwd=ROOT,
                              capture_output=True, text=True, timeout=40)
        if proc.returncode:
            raise AssertionError(proc.stderr)
        cls.orm = json.loads(proc.stdout)

    def test_01_imports_reales_sin_conexion_ni_ddl(self):
        self.assertEqual(self.orm["effects"], 0)
        self.assertTrue(self.orm["full_package_imported"])

    def test_02_registro_completo_27_clases_y_tablas(self):
        self.assertEqual(self.orm["mapped_class_count"], 27)
        self.assertEqual(len(self.orm["tables"]), 27)

    def test_03_sin_tablas_duplicadas_en_fuente(self):
        nombres = []
        for archivo in MODELOS.glob("*.py"):
            for node in ast.walk(ast.parse(archivo.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
                    nombres.append(ast.literal_eval(node.value))
        self.assertEqual(len(nombres), 27)
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_04_fk_resueltas(self):
        self.assertEqual(self.orm["unresolved_fk"], [])

    def test_05_ddl_compilable_solo_en_memoria(self):
        self.assertEqual(set(self.orm["tables"]), set(self.orm["compiled"]))
        self.assertEqual(self.orm["compile_errors"], {})

    def test_06_mappers_validos(self):
        self.assertIsNone(self.orm["mapping_error"])

    def test_07_preflight_valida_cuatro_modulos(self):
        self.assertEqual(self.orm["blocked_modules"], [])
        for nombre in PENDIENTES:
            self.assertTrue((MODELOS / (nombre + ".py")).exists())

    def test_08_tipos_y_restricciones_existentes(self):
        columnas = self.orm["tables"]["unidad_documental"]["columns"]
        self.assertEqual(columnas["id"]["type"], "INTEGER")
        self.assertEqual(columnas["caja_definitiva"]["type"], "VARCHAR(20)")
        self.assertEqual(columnas["periodo_id"]["type"], "INTEGER")
        self.assertTrue(columnas["periodo_id"]["nullable"])
        self.assertTrue(columnas["codigo_carpeta"]["unique"])
        for nombre, tabla in self.orm["tables"].items():
            self.assertEqual(tabla["pk"], ["fecha", "proveedor"] if nombre == "consumo_lector" else [{"parametro_contrato": "clave",
                "obligacion_contrato": "numero"}.get(nombre, "id")])

    def test_09_back_populates_confirmados(self):
        relaciones = {}
        for node in ast.walk(arbol("geology/modelos/unidad.py")):
            if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id == "relationship":
                    relaciones[node.target.id] = {k.arg: ast.literal_eval(k.value) for k in node.value.keywords}
        self.assertEqual(relaciones["trazabilidad"]["back_populates"], "expediente")
        self.assertEqual(relaciones["trazabilidad"]["order_by"], "Trazabilidad.fecha")
        self.assertEqual(relaciones["tramites"]["back_populates"], "expediente")
        self.assertEqual(relaciones["expediente"]["back_populates"], "tramites")
        self.assertNotIn("periodo", relaciones)
        self.assertNotIn("caja", relaciones)

    def test_10_consumo_tabla_y_longitud_confirmadas(self):
        strings = [n.value for n in ast.walk(arbol("geology/nucleo/estructura.py"))
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertIn("ALTER TABLE consumo_lector ALTER COLUMN proveedor TYPE VARCHAR(120)", strings)
        tree = arbol("geology/dominio/lectores.py")
        llamadas = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == "ConsumoModelo"]
        self.assertEqual([{k.arg for k in n.keywords} for n in llamadas], [{"fecha", "proveedor", "peticiones"}])

    def test_11_contrato_trazabilidad_errores_texto(self):
        tree = arbol("geology/rutas/unidades.py")
        huella = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_huella")
        llamada = next(n for n in ast.walk(huella) if isinstance(n, ast.Call)
                       and isinstance(n.func, ast.Name) and n.func.id == "Trazabilidad")
        self.assertEqual({k.arg for k in llamada.keywords}, {
            "expediente", "estado_anterior", "estado_nuevo", "accion", "usuario", "motivo", "errores"})
        self.assertIn("json.dumps", ast.unparse(huella))

    def test_12_jerarquia_consultada_sin_fk_fondo_demostrada(self):
        fuente = (ROOT / "geology/rutas/unidades.py").read_text(encoding="utf-8")
        for enlace in ("Subserie.serie_id == Serie.id", "Serie.seccion_id == Seccion.id",
                       "Seccion.periodo_id == Periodo.id"):
            self.assertIn(enlace, fuente)
        self.assertIn("exp.periodo.numero_romano", fuente)
        # El enlace Fondo-Periodo ahora es una decisión local explícita, no evidencia original.
        self.assertIn("fondo_id", (MODELOS / "valoracion.py").read_text(encoding="utf-8"))



if __name__ == "__main__":
    unittest.main()
