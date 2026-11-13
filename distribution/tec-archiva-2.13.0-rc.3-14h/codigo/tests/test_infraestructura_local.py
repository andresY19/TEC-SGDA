"""Pruebas unitarias sin servidor, worker, conexiones ni DDL real.

Ejecutar con Python -B en un contenedor sin red y sin montar .env.
Usa unittest de la biblioteca estándar; no requiere instalar pytest.
"""
from __future__ import annotations

import importlib
import inspect
import logging
import os
import socket
import sys
import unittest
from unittest.mock import Mock, patch


ENTORNO = {
    "DATABASE_URL": "postgresql+psycopg2://synthetic:synthetic-password@db.invalid:5432/synthetic",
    "DB_POOL_SIZE": "3", "DB_MAX_OVERFLOW": "2",
    "GEOLOGY_LOCAL_PROJECT": "geology-unit-local",
    "GEOLOGY_COLA": "geology-unit-local-tasks",
    "GEOLOGY_ENTORNO": "test",
    "CELERY_BROKER_URL": "redis://redis.invalid:6379/14",
    "CELERY_RESULT_BACKEND": "redis://redis.invalid:6379/15",
    "ZONA_HORARIA": "America/Bogota",
}


class Infraestructura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entorno = patch.dict(os.environ, ENTORNO, clear=True)
        cls.entorno.start()
        # Un fallo de cualquier guardia hace fallar la suite: nunca se toca infraestructura.
        cls.guardias = [
            patch.object(socket.socket, "connect", side_effect=AssertionError("Red prohibida")),
            patch("socket.create_connection", side_effect=AssertionError("Red prohibida")),
            patch("psycopg2.connect", side_effect=AssertionError("DBAPI prohibida")),
            patch("sqlalchemy.engine.Engine.connect", side_effect=AssertionError("Conexión prohibida")),
            patch("sqlalchemy.sql.schema.MetaData.create_all", side_effect=AssertionError("DDL prohibido")),
            patch("celery.app.task.Task.apply_async", side_effect=AssertionError("Publicación prohibida")),
            patch("celery.app.task.Task.apply", side_effect=AssertionError("Ejecución prohibida")),
            patch("kombu.Connection.connect", side_effect=AssertionError("Broker prohibido")),
        ]
        cls.espias = [g.start() for g in cls.guardias]
        cls.bd = importlib.import_module("geology.nucleo.bd")
        cls.cola = importlib.import_module("geology.nucleo.cola")

    @classmethod
    def tearDownClass(cls):
        cls.bd.motor.dispose()
        cls.cola.celery_app.close()
        for g in reversed(cls.guardias):
            g.stop()
        cls.entorno.stop()

    def test_01_imports_sin_efectos(self):
        for espia in self.espias:
            espia.assert_not_called()
        self.assertNotIn("geology.modelos", sys.modules)
        self.assertNotIn("geology.main", sys.modules)
        self.assertNotIn("geology.nucleo.ajustes", sys.modules)
        self.assertNotIn("geology.trabajos", sys.modules)
        self.assertEqual(len(self.bd.Base.metadata.tables), 0)

    def test_02_configuracion_sqlalchemy(self):
        self.assertEqual(self.bd.motor.dialect.name, "postgresql")
        self.assertEqual(self.bd.motor.url.host, "db.invalid")
        self.assertEqual(self.bd.motor.pool.size(), 3)
        self.assertEqual(self.bd.motor.pool._max_overflow, 2)
        self.assertTrue(self.bd.motor.hide_parameters)
        self.assertFalse(self.bd.motor.echo)
        self.assertIs(self.bd.SesionLocal.kw["bind"], self.bd.motor)
        self.assertFalse(self.bd.SesionLocal.kw["autoflush"])
        self.assertFalse(self.bd.SesionLocal.kw["expire_on_commit"])

    def test_03_sessionmaker_no_conecta(self):
        sesion = self.bd.SesionLocal()
        try:
            self.assertFalse(sesion.in_transaction())
        finally:
            sesion.close()

    def test_04_sesion_normal_cierra_sin_commit(self):
        sesion = Mock()
        with patch.object(self.bd, "SesionLocal", return_value=sesion):
            dependencia = self.bd.obtener_sesion()
            self.assertIs(next(dependencia), sesion)
            with self.assertRaises(StopIteration):
                next(dependencia)
        sesion.close.assert_called_once()
        sesion.commit.assert_not_called()
        sesion.rollback.assert_not_called()

    def test_05_excepcion_hace_rollback_y_cierra(self):
        sesion = Mock()
        fallo = ValueError("fallo sintético")
        with patch.object(self.bd, "SesionLocal", return_value=sesion):
            dependencia = self.bd.obtener_sesion()
            next(dependencia)
            with self.assertRaises(ValueError) as obtenido:
                dependencia.throw(fallo)
        self.assertIs(obtenido.exception, fallo)
        sesion.rollback.assert_called_once()
        sesion.close.assert_called_once()
        sesion.commit.assert_not_called()

    def test_06_fallo_rollback_conserva_excepcion_y_cierra(self):
        sesion = Mock()
        sesion.rollback.side_effect = RuntimeError("sensitive-diagnostic")
        with patch.object(self.bd, "SesionLocal", return_value=sesion), self.assertLogs(self.bd._log, logging.WARNING) as logs:
            dependencia = self.bd.obtener_sesion()
            next(dependencia)
            with self.assertRaises(ValueError):
                dependencia.throw(ValueError("original"))
        self.assertNotIn("sensitive-diagnostic", " ".join(logs.output))
        sesion.close.assert_called_once()

    def test_07_url_invalida_no_filtra_secretos(self):
        for valor in ("", "sqlite://", "invalid-sensitive-diagnostic", "postgresql+psycopg2://u:<CLAVE_LOCAL>@db/test"):
            with self.subTest(valor=bool(valor)), patch.dict(os.environ, {"DATABASE_URL": valor}):
                with self.assertRaises(RuntimeError) as error:
                    self.bd._crear_motor()
                self.assertNotIn("invalid-sensitive", str(error.exception))
                self.assertNotIn("<CLAVE_LOCAL>", str(error.exception))
                self.assertTrue(error.exception.__suppress_context__)

    def test_08_error_driver_sanitizado(self):
        with patch.object(self.bd, "create_engine", side_effect=RuntimeError("sensitive-diagnostic")):
            with self.assertRaises(RuntimeError) as error:
                self.bd._crear_motor()
        self.assertNotIn("sensitive-diagnostic", str(error.exception))

    def test_09_pool_invalido_no_crea_motor(self):
        for valor in ("-1", "0", "not-a-number"):
            with patch.dict(os.environ, {"DB_POOL_SIZE": valor}), patch.object(self.bd, "create_engine") as crear:
                with self.assertRaises(RuntimeError):
                    self.bd._crear_motor()
                crear.assert_not_called()

    def test_10_modelos_incompletos_no_se_importan(self):
        with patch.object(self.bd.Path, "is_file", side_effect=lambda path: path.stem not in {"valoracion", "bitacora", "consumo_lector", "caja"}, autospec=True), patch.object(self.bd.importlib, "import_module") as importar:
            with self.assertRaisesRegex(RuntimeError, "valoracion.*bitacora.*consumo_lector.*caja"):
                self.bd.registrar_modelos()
        importar.assert_not_called()

    def test_11_ddl_requiere_opt_in(self):
        with patch.object(self.bd, "registrar_modelos") as registrar, patch.object(self.bd.Base.metadata, "create_all") as crear:
            with self.assertRaisesRegex(RuntimeError, "DDL deshabilitado"):
                self.bd.crear_tablas()
        registrar.assert_not_called()
        crear.assert_not_called()

    def test_12_ni_opt_in_permite_modelos_faltantes(self):
        with patch.dict(os.environ, {"GEOLOGY_PERMITIR_DDL": "1"}), patch.object(self.bd.Path, "is_file", return_value=False), patch.object(self.bd.Base.metadata, "create_all") as crear:
            with self.assertRaisesRegex(RuntimeError, "Registro de modelos incompleto"):
                self.bd.crear_tablas(autorizacion_local=True)
        crear.assert_not_called()

    def test_12a_archivos_presentes_no_bastan_sin_mapeadores(self):
        # Simula solo el resultado del cargador, sin crear módulos ni modelos sustitutos.
        with patch.object(self.bd.Path, "is_file", return_value=True), patch.object(self.bd.importlib, "import_module", return_value=object()), patch.object(self.bd.Base.metadata, "create_all") as crear:
            with self.assertRaisesRegex(RuntimeError, "registro completo de modelos ORM"):
                self.bd.registrar_modelos()
        crear.assert_not_called()

    def test_13_contrato_ddl_solo_con_dobles(self):
        # Ambos pasos son mocks: no hay creación de tablas ni metadatos sintéticos persistidos.
        orden = Mock()
        with patch.dict(os.environ, {"GEOLOGY_PERMITIR_DDL": "1"}), patch.object(self.bd, "registrar_modelos") as registrar, patch.object(self.bd.Base.metadata, "create_all") as crear:
            orden.attach_mock(registrar, "registro")
            orden.attach_mock(crear, "ddl")
            self.bd.crear_tablas(autorizacion_local=True)
            self.assertEqual([c[0] for c in orden.mock_calls], ["registro", "ddl"])
            crear.assert_called_once_with(bind=self.bd.motor)

    def test_14_error_ddl_sanitizado_con_doble(self):
        with patch.dict(os.environ, {"GEOLOGY_PERMITIR_DDL": "1"}), patch.object(self.bd, "registrar_modelos"), patch.object(self.bd.Base.metadata, "create_all", side_effect=RuntimeError("sensitive-diagnostic")):
            with self.assertRaises(RuntimeError) as error:
                self.bd.crear_tablas(autorizacion_local=True)
        self.assertNotIn("sensitive-diagnostic", str(error.exception))

    def test_15_verificar_conexion_solo_select_con_doble(self):
        conexion = Mock()
        conexion.execute.return_value.scalar_one.return_value = 1
        contexto = Mock()
        contexto.__enter__ = Mock(return_value=conexion)
        contexto.__exit__ = Mock(return_value=False)
        with patch.object(self.bd.motor, "connect", return_value=contexto):
            self.assertTrue(self.bd.verificar_conexion())
        self.assertEqual(str(conexion.execute.call_args.args[0]), "SELECT 1")
        contexto.__exit__.assert_called_once()

    def test_16_verificar_conexion_falla_sin_filtrar(self):
        with patch.object(self.bd.motor, "connect", side_effect=RuntimeError("sensitive-diagnostic")), self.assertLogs(self.bd._log, logging.WARNING) as logs:
            self.assertFalse(self.bd.verificar_conexion())
        self.assertNotIn("sensitive-diagnostic", " ".join(logs.output))

    def test_17_celery_configuracion_exclusiva(self):
        app = self.cola.celery_app
        c = app.conf
        self.assertEqual(c.broker_url, ENTORNO["CELERY_BROKER_URL"])
        self.assertEqual(c.result_backend, ENTORNO["CELERY_RESULT_BACKEND"])
        self.assertEqual(c.task_default_queue, ENTORNO["GEOLOGY_COLA"])
        self.assertEqual([q.name for q in c.task_queues], [ENTORNO["GEOLOGY_COLA"]])
        self.assertFalse(c.task_create_missing_queues)
        self.assertFalse(c.task_always_eager)
        self.assertFalse(c.worker_enable_remote_control)
        self.assertEqual(c.beat_schedule, {})
        self.assertEqual(c.accept_content, ["json"])
        self.assertEqual(tuple(c.include), ("geology.trabajos",))
        self.assertEqual(c.broker_transport_options["global_keyprefix"], "geology-unit-local:")
        self.assertEqual(c.result_backend_transport_options["global_keyprefix"], "geology-unit-local:")

    def test_18_rutas_solo_cola_local(self):
        app = self.cola.celery_app
        for nombre in self.cola.NOMBRES_TAREAS:
            ruta = app.amqp.router.route({}, nombre, args=(), kwargs={})
            self.assertEqual(ruta["queue"].name, ENTORNO["GEOLOGY_COLA"])
            self.assertEqual(ruta["routing_key"], ENTORNO["GEOLOGY_COLA"])
        with self.assertRaises(KeyError):
            app.amqp.queues["otra-aplicacion"]

    def test_19_redis_invalido_sanitizado(self):
        for url in ("", "http://sensitive-diagnostic/0", "redis://redis.invalid:bad/0", "redis://redis.invalid/0?secret=sensitive-diagnostic"):
            with patch.dict(os.environ, {"CELERY_BROKER_URL": url}):
                with self.assertRaises(RuntimeError) as error:
                    self.cola._redis("CELERY_BROKER_URL")
                self.assertNotIn("sensitive-diagnostic", str(error.exception))

    def test_20_registro_tareas_reales_sin_ejecutarlas(self):
        with patch.object(self.bd, "SesionLocal", side_effect=AssertionError("Tarea ejecutada")), patch("celery.app.task.Task.__call__", side_effect=AssertionError("Tarea ejecutada")):
            nombres = self.cola.registrar_tareas()
            self.assertEqual(nombres, self.cola.registrar_tareas())
        tareas = self.cola.celery_app.tasks
        self.assertEqual(set(nombres), {"geology.levantar_hoja", "geology.preparar_digitalizacion", "geology.ping"})
        self.assertIn("expediente_id", inspect.signature(tareas["geology.levantar_hoja"].run).parameters)
        self.assertIn("archivo_id", inspect.signature(tareas["geology.preparar_digitalizacion"].run).parameters)
        self.assertEqual(len(inspect.signature(tareas["geology.ping"].run).parameters), 0)
        self.assertNotIn("geology.modelos", sys.modules)
        self.assertNotIn("geology.main", sys.modules)

    def test_21_guardias_nunca_fueron_usadas(self):
        for espia in self.espias:
            espia.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
