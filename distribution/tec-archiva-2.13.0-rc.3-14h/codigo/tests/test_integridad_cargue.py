"""Ejecuta el cuerpo REAL del cargue con una sesión SQL simulada y PDFs sintéticos.

La extracción AST evita importar rutas/modelos incompletos. Los dobles existen
solo en estas pruebas: no son implementaciones de módulos de dominio ausentes.
No importa ni ejecuta el helper que publica tareas posteriores al commit.
"""
from __future__ import annotations

import ast
import asyncio
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import column
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

from geology.dominio import division
from geology.dominio.codigos import partes_de_archivo
from geology.dominio.estados import Estado, Usuario, Rol, motivo_de_rechazo_de_carga
from test_procesamiento_documental import crear_pdf, sha, firmas


class Datos:
    def __init__(self, **valores):
        self.__dict__.update(id=None, expediente_id=None, codigo_carpeta=None, fragmento=0,
                             sha256=None, sha256_origen=None, ruta=None, nombre_original=None,
                             tamano_bytes=None, ruta_matriz=None, ruta_consulta=None, ruta_texto=None,
                             definitiva=False, paginas=None, pagina_inicial=None, pagina_final=None,
                             describio=None, estado=Estado.EN_COLA.value, tramites=[],
                             caja_origen="AC-CJ-00001", caja_trabajo="733-CJ-00001",
                             periodo="I", folios=5, asunto="Expediente sintético")
        self.__dict__.update(valores)


class Archivo(Datos):
    codigo_carpeta, sha256, sha256_origen = column("codigo_carpeta"), column("sha256"), column("sha256_origen")


class Expediente(Datos):
    codigo_carpeta = column("codigo_carpeta")


class UnidadInventario(Datos):
    codigo_carpeta = column("codigo_carpeta")


class Trazabilidad(Datos):
    pass


def coincide(expresion, fila):
    if isinstance(expresion, BooleanClauseList):
        valores = [coincide(x, fila) for x in expresion.clauses]
        return any(valores) if expresion.operator is operators.or_ else all(valores)
    if isinstance(expresion, BinaryExpression):
        return expresion.operator(getattr(fila, expresion.left.name), expresion.right.value)
    raise AssertionError("Predicado SQL fuera del doble de prueba")


class Consulta:
    def __init__(self, sesion, modelo):
        self.sesion, self.modelo, self.filtros = sesion, modelo, []

    def filter(self, *condiciones):
        self.filtros.extend(condiciones)
        return self

    def with_for_update(self):
        self.sesion.bloqueo_solicitado = True
        return self

    def all(self):
        filas = self.sesion.filas[self.modelo] + [x for x in self.sesion.agregadas if type(x) is self.modelo]
        return [x for x in filas if x not in self.sesion.eliminadas and all(coincide(c, x) for c in self.filtros)]

    def first(self):
        return next(iter(self.all()), None)

    def count(self):
        return len(self.all())


class SesionSimulada:
    def __init__(self, archivos=(), expediente=None):
        self.filas = {Archivo: list(archivos), Expediente: [expediente] if expediente else [],
                      UnidadInventario: [UnidadInventario(id=1, codigo_carpeta="AC-CP-00374")], Trazabilidad: []}
        self.snapshot = [(x, copy.deepcopy(x.__dict__)) for grupo in self.filas.values() for x in grupo]
        self.agregadas, self.eliminadas = [], []
        self.commit_calls = self.rollback_calls = self.flush_calls = self.mutaciones = 0
        self.confirmada = self.bloqueo_solicitado = False
        self.fallo_commit = None
        self.fallo_flush = None

    def query(self, modelo):
        return Consulta(self, modelo)

    def add(self, registro):
        self.agregadas.append(registro)
        self.mutaciones += 1

    def add_all(self, registros):
        for r in registros:
            self.add(r)

    def delete(self, registro):
        self.eliminadas.append(registro)
        self.mutaciones += 1

    def flush(self):
        self.flush_calls += 1
        if self.flush_calls == self.fallo_flush:
            raise OSError("synthetic database flush failure")
        for i, r in enumerate(self.agregadas, 100):
            if r.id is None:
                r.id = i

    def commit(self):
        self.commit_calls += 1
        if self.fallo_commit == "antes":
            raise OSError("synthetic connection lost before commit")
        for tipo in self.filas:
            self.filas[tipo] = self.query(tipo).all()
        self.agregadas, self.eliminadas = [], []
        self.confirmada = True
        if self.fallo_commit == "despues":
            raise OSError("synthetic lost acknowledgement after commit")

    def rollback(self):
        self.rollback_calls += 1
        if not self.confirmada:
            self.agregadas, self.eliminadas = [], []
            for objeto, atributos in self.snapshot:
                objeto.__dict__.clear()
                objeto.__dict__.update(copy.deepcopy(atributos))


class IntegridadCargue(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="geology-integrity-synthetic-")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.almacen = self.raiz / "deposito"
        self.almacen.mkdir()
        self.nuevo = self.raiz / "nuevo.pdf"
        crear_pdf(self.nuevo, 5)
        self.nuevo_sha = sha(self.nuevo)
        self.quien = Usuario("Persona sintética", "synthetic@example.invalid", rol=Rol.EQUIPO)
        self.post_commit_calls = 0
        def tras_commit(db, exp, registros, carpeta, reemplazar, quien):
            self.assertTrue(db.confirmada)
            self.post_commit_calls += 1
            return False, None, "", len(db.filas[Archivo])
        ruta = Path(division.__file__).parents[1] / "rutas" / "cargue.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))
        nombres = {"_OperacionCargue", "_datos_archivo_archivado", "es_el_mismo_fichero", "_limpiar", "cargar", "cargar_documento"}
        nodos = [n for n in arbol.body if isinstance(n, ast.ImportFrom) and n.module == "__future__"]
        for n in arbol.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name in nombres:
                n.decorator_list = []
                nodos.append(n)
        self.codigo = dict(Path=Path, division=division, json=json, tempfile=tempfile, datetime=datetime,
                           timezone=timezone, hashlib=hashlib, os=os, re=re, UploadFile=UploadFile,
                           File=File, Form=Form, Depends=Depends, obtener_sesion=lambda: None,
                           usuario_actual=lambda: None, HTTPException=HTTPException,
                           Archivo=Archivo, Expediente=Expediente, UnidadInventario=UnidadInventario,
                           Trazabilidad=Trazabilidad, partes_de_archivo=partes_de_archivo,
                           Estado=Estado, motivo_de_rechazo_de_carga=motivo_de_rechazo_de_carga,
                           ALMACEN=self.almacen, TROZO=1024, _log=logging.getLogger("test.integridad"),
                           _tras_confirmar_cargue=tras_commit)
        exec(compile(ast.Module(body=nodos, type_ignores=[]), str(ruta), "exec"), self.codigo)
        self.limite = patch.object(division, "PAGINAS_POR_PARTE", 2)
        self.limite.start()
        self.addCleanup(self.limite.stop)

    def upload(self, datos=None, nombre="CARPETA_00374.pdf"):
        return UploadFile(file=io.BytesIO(self.nuevo.read_bytes() if datos is None else datos), filename=nombre)

    def cargar(self, db, archivo=None, **kwargs):
        return asyncio.run(self.codigo["cargar"](archivo or self.upload(), db, self.quien,
                                                reemplazar=kwargs.get("reemplazar", False),
                                                definitiva=kwargs.get("definitiva", False)))

    def diarios(self):
        return [json.loads(p.read_text()) for p in sorted(self.almacen.glob("operaciones/*/operacion.json"))]

    def anterior(self):
        original = self.almacen / "AC-CP-00374_CARPETA_00374.pdf"
        crear_pdf(original, 3)
        adicionales = []
        for sufijo in ("matriz.pdf", "consulta.pdf", "texto.txt"):
            p = self.almacen / sufijo
            p.write_bytes(b"synthetic-existing-" + sufijo.encode())
            adicionales.append(p)
        a = Archivo(id=10, expediente_id=20, codigo_carpeta="AC-CP-00374", ruta=str(original),
                    sha256=sha(original), tamano_bytes=original.stat().st_size, nombre_original=original.name,
                    ruta_matriz=str(adicionales[0]), ruta_consulta=str(adicionales[1]), ruta_texto=str(adicionales[2]))
        exp = Expediente(id=20, codigo_carpeta="AC-CP-00374")
        archivos = {p: sha(p) for p in [original, *adicionales]}
        return a, exp, archivos

    def assertConservados(self, archivos):
        for p, h in archivos.items():
            self.assertTrue(p.is_file())
            self.assertEqual(sha(p), h)

    def assertReferencias(self, db):
        for a in db.filas[Archivo]:
            self.assertTrue(Path(a.ruta).is_file())
            self.assertEqual(sha(a.ruta), a.sha256)
            self.assertEqual(Path(a.ruta).stat().st_size, a.tamano_bytes)

    def assertOriginalArchivado(self):
        originales = list(self.almacen.glob("operaciones/*/original.pdf"))
        self.assertTrue(originales)
        self.assertTrue(any(sha(p) == self.nuevo_sha for p in originales))
        self.assertEqual(sha(self.nuevo), self.nuevo_sha)

    def test_cargue_sin_division_exitoso(self):
        db = SesionSimulada()
        with patch.object(division, "PAGINAS_POR_PARTE", 250):
            r = self.cargar(db, definitiva=True)
        self.assertFalse(r["dividido_por_sistema"])
        self.assertTrue(db.bloqueo_solicitado)
        self.assertEqual(db.commit_calls, 1)
        self.assertEqual(len(db.filas[Archivo]), 1)
        self.assertTrue(db.filas[Archivo][0].definitiva)
        self.assertReferencias(db)
        self.assertOriginalArchivado()
        self.assertEqual(self.diarios()[0]["estado"], "confirmada")

    def test_cargue_division_exitoso_y_sha_original(self):
        db = SesionSimulada()
        r = self.cargar(db)
        self.assertTrue(r["dividido_por_sistema"])
        self.assertEqual(len(db.filas[Archivo]), 3)
        self.assertEqual(r["sha256_original"], self.nuevo_sha)
        self.assertEqual(sha(r["original_conservado"]), self.nuevo_sha)
        self.assertTrue(all(a.sha256_origen == self.nuevo_sha for a in db.filas[Archivo]))
        self.assertEqual([p for a in db.filas[Archivo] for p in firmas(a.ruta)], firmas(self.nuevo))
        self.assertReferencias(db)
        self.assertOriginalArchivado()
        self.assertEqual(self.post_commit_calls, 1)

    def test_division_fallida_no_inserta_y_conserva_original(self):
        db = SesionSimulada()
        with patch.object(division, "dividir", side_effect=OSError("synthetic disk failure")), self.assertRaises(HTTPException) as e:
            self.cargar(db)
        self.assertEqual(e.exception.status_code, 503)
        self.assertEqual(db.filas[Archivo], [])
        self.assertEqual(db.mutaciones, 0)
        self.assertEqual(db.commit_calls, 0)
        self.assertOriginalArchivado()
        self.assertEqual(self.diarios()[0]["estado"], "revertida_antes_commit")

    def test_division_vacia_no_registra_completo_como_fallback(self):
        db = SesionSimulada()
        with patch.object(division, "dividir", return_value=[]), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.mutaciones, 0)
        self.assertOriginalArchivado()

    def test_parte_alterada_no_llega_a_sql(self):
        real = division.dividir
        def alterar(*args):
            partes = real(*args)
            with partes[0].ruta.open("ab") as f:
                f.write(b"\n%synthetic-tamper\n")
            return partes
        db = SesionSimulada()
        with patch.object(division, "dividir", side_effect=alterar), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.mutaciones, 0)
        self.assertOriginalArchivado()

    def test_rango_de_parte_invalido_no_llega_a_sql(self):
        real = division.dividir
        def alterar(*args):
            partes = real(*args)
            return [replace(partes[0], pagina_inicial=2), *partes[1:]]
        db = SesionSimulada()
        with patch.object(division, "dividir", side_effect=alterar), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.mutaciones, 0)

    def test_colision_partes_no_sobrescribe_ni_inserta(self):
        real = division.dividir
        ajeno = []
        def colision(origen, carpeta, destino, nombre):
            p = destino / f"{carpeta}_parte_00001_documento.pdf"
            p.write_bytes(b"foreign-existing-synthetic")
            ajeno.append(p)
            return real(origen, carpeta, destino, nombre)
        db = SesionSimulada()
        with patch.object(division, "dividir", side_effect=colision), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(ajeno[0].read_bytes(), b"foreign-existing-synthetic")
        self.assertEqual(db.mutaciones, 0)
        self.assertOriginalArchivado()

    def test_nombre_del_cliente_no_controla_la_ruta(self):
        db = SesionSimulada()
        r = self.cargar(db, self.upload(nombre="../../CARPETA_00374.pdf"))
        self.assertEqual(Path(r["original_conservado"]).name, "original.pdf")
        self.assertTrue(Path(r["original_conservado"]).is_relative_to(self.almacen))
        self.assertReferencias(db)

    def test_error_escritura_original_revierte_y_no_deja_parcial(self):
        class UploadFallido:
            filename = "CARPETA_00374.pdf"
            contador = 0
            async def read(self, n):
                self.contador += 1
                if self.contador == 1:
                    return b"synthetic-partial"
                raise OSError("synthetic write/read failure")
        db = SesionSimulada()
        with self.assertRaises(HTTPException):
            self.cargar(db, UploadFallido())
        self.assertEqual(list(self.almacen.glob("operaciones/*/.original.part")), [])
        self.assertEqual(db.mutaciones, 0)
        self.assertEqual(db.rollback_calls, 1)

    def test_error_sql_flush_conserva_original_y_no_confirma(self):
        db = SesionSimulada()
        db.fallo_flush = 2
        with self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.filas[Archivo], [])
        self.assertEqual(db.filas[Expediente], [])
        self.assertEqual(db.rollback_calls, 1)
        self.assertEqual(db.commit_calls, 0)
        self.assertOriginalArchivado()

    def test_cambio_de_parte_tras_flush_impide_commit(self):
        db = SesionSimulada()
        real = db.flush
        def flush():
            real()
            if db.flush_calls == 2:
                a = next(a for a in db.agregadas if isinstance(a, Archivo))
                with Path(a.ruta).open("ab") as f:
                    f.write(b"\n%synthetic-change-before-commit\n")
        with patch.object(db, "flush", side_effect=flush), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.commit_calls, 0)
        self.assertEqual(db.rollback_calls, 1)
        self.assertEqual(db.filas[Archivo], [])
        self.assertOriginalArchivado()

    def test_parte_fuera_de_operacion_no_se_registra_ni_se_borra(self):
        real = division.dividir
        def ajena(*args):
            partes = real(*args)
            return [replace(partes[0], ruta=self.nuevo), *partes[1:]]
        db = SesionSimulada()
        with patch.object(division, "dividir", side_effect=ajena), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(sha(self.nuevo), self.nuevo_sha)
        self.assertEqual(db.mutaciones, 0)
        self.assertOriginalArchivado()

    def test_duplicado_de_otra_carpeta_no_se_borra(self):
        otra = self.almacen / "otro-documento.pdf"
        otra.write_bytes(self.nuevo.read_bytes())
        registro = Archivo(id=10, codigo_carpeta="AC-CP-99999", ruta=str(otra),
                           sha256=sha(otra), tamano_bytes=otra.stat().st_size)
        db = SesionSimulada([registro])
        with self.assertRaises(HTTPException) as e:
            self.cargar(db)
        self.assertEqual(e.exception.status_code, 409)
        self.assertEqual(sha(otra), self.nuevo_sha)
        self.assertEqual(db.filas[Archivo], [registro])
        self.assertEqual(db.mutaciones, 0)

    def test_rollback_fallido_no_se_declara_confirmado(self):
        viejo, exp, archivos = self.anterior()
        db = SesionSimulada([viejo], exp)
        db.fallo_flush = 1
        with patch.object(db, "rollback", side_effect=OSError("synthetic rollback failure")), self.assertLogs("test.integridad", logging.ERROR):
            with self.assertRaises(HTTPException):
                self.cargar(db, reemplazar=True)
        self.assertConservados(archivos)
        self.assertOriginalArchivado()
        diario = self.diarios()[0]
        self.assertEqual(diario["estado"], "rollback_no_confirmado")
        self.assertFalse(diario["rollback_confirmado"])

    def test_publicacion_original_fallida_conserva_temporal_completo(self):
        real = division._publicar_atomico
        ajenos = []
        def publicar(temporal, destino):
            if destino.name == "original.pdf":
                destino.write_bytes(b"foreign-synthetic-original")
                ajenos.append(destino)
            return real(temporal, destino)
        db = SesionSimulada()
        with patch.object(division, "_publicar_atomico", side_effect=publicar), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(ajenos[0].read_bytes(), b"foreign-synthetic-original")
        temporal = next(self.almacen.glob("operaciones/*/.original.part"))
        self.assertEqual(sha(temporal), self.nuevo_sha)
        self.assertEqual(self.diarios()[0]["original_temporal"]["sha256"], self.nuevo_sha)
        self.assertEqual(db.mutaciones, 0)

    def test_error_diario_al_publicar_original_conserva_ambos_enlaces(self):
        clase = self.codigo["_OperacionCargue"]
        real = clase.estado
        def estado(op, nombre, **cambios):
            if nombre == "original_conservado":
                raise OSError("synthetic journal failure after source publication")
            return real(op, nombre, **cambios)
        db = SesionSimulada()
        with patch.object(clase, "estado", new=estado), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertOriginalArchivado()
        temporal = next(self.almacen.glob("operaciones/*/.original.part"))
        self.assertEqual(sha(temporal), self.nuevo_sha)
        self.assertEqual(db.mutaciones, 0)

    def test_error_sql_commit_antes_no_borra_archivos(self):
        db = SesionSimulada()
        db.fallo_commit = "antes"
        with self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.filas[Archivo], [])
        self.assertOriginalArchivado()
        diario = self.diarios()[0]
        self.assertEqual(diario["estado"], "resultado_sql_desconocido")
        self.assertTrue(diario["commit_intentado"])
        self.assertTrue(all(Path(a["ruta"]).is_file() for a in diario["registros"]))

    def test_commit_aplicado_respuesta_perdida_conserva_referencias(self):
        db = SesionSimulada()
        db.fallo_commit = "despues"
        with self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertTrue(db.confirmada)
        self.assertReferencias(db)
        self.assertOriginalArchivado()
        self.assertEqual(self.diarios()[0]["estado"], "resultado_sql_desconocido")
        self.assertEqual(self.post_commit_calls, 0)

    def test_interrupcion_controlada_durante_division(self):
        Interrupcion = asyncio.CancelledError
        real, contador = division._publicar_atomico, 0
        def publicar(temporal, destino):
            nonlocal contador
            if destino.name != "original.pdf":
                contador += 1
                if contador == 2:
                    raise Interrupcion()
            real(temporal, destino)
        db = SesionSimulada()
        with patch.object(division, "_publicar_atomico", side_effect=publicar), self.assertRaises(Interrupcion):
            self.cargar(db)
        self.assertOriginalArchivado()
        self.assertEqual(list(self.almacen.glob("operaciones/*/*parte*.pdf")), [])
        self.assertEqual(db.mutaciones, 0)
        self.assertEqual(db.rollback_calls, 1)

    def test_reintento_tras_rollback_no_pisa_operacion_anterior(self):
        db = SesionSimulada()
        db.fallo_commit = "antes"
        with self.assertRaises(HTTPException):
            self.cargar(db)
        existentes = {p: sha(p) for p in self.almacen.rglob("*.pdf")}
        db.fallo_commit = None
        self.cargar(db)
        self.assertConservados(existentes)
        self.assertReferencias(db)
        self.assertEqual(len(self.diarios()), 2)

    def test_reintento_tras_exito_es_duplicado_sin_cambios(self):
        db = SesionSimulada()
        self.cargar(db)
        existentes = {p: sha(p) for p in self.almacen.rglob("*") if p.is_file()}
        with self.assertRaises(HTTPException) as e:
            self.cargar(db)
        self.assertEqual(e.exception.status_code, 409)
        self.assertConservados(existentes)
        self.assertEqual(len(self.diarios()), 1)

    def test_reemplazo_fallido_division_conserva_anteriores(self):
        viejo, exp, archivos = self.anterior()
        db = SesionSimulada([viejo], exp)
        with patch.object(division, "dividir", side_effect=OSError("synthetic division failure")), self.assertRaises(HTTPException):
            self.cargar(db, reemplazar=True)
        self.assertConservados(archivos)
        self.assertEqual(db.filas[Archivo], [viejo])
        self.assertEqual(db.mutaciones, 0)
        self.assertOriginalArchivado()

    def test_reemplazo_fallido_sql_restaura_filas_y_conserva_archivos(self):
        viejo, exp, archivos = self.anterior()
        db = SesionSimulada([viejo], exp)
        db.fallo_commit = "antes"
        with self.assertRaises(HTTPException):
            self.cargar(db, reemplazar=True)
        self.assertConservados(archivos)
        self.assertEqual(db.filas[Archivo], [viejo])
        self.assertReferencias(db)
        self.assertOriginalArchivado()
        self.assertTrue(self.diarios()[0]["anteriores"])

    def test_reemplazo_exitoso_conserva_incluso_archivos_previos(self):
        viejo, exp, archivos = self.anterior()
        db = SesionSimulada([viejo], exp)
        r = self.cargar(db, reemplazar=True)
        self.assertTrue(r["reemplazo"])
        self.assertConservados(archivos)
        self.assertNotIn(viejo, db.filas[Archivo])
        self.assertEqual(len(db.filas[Archivo]), 3)
        self.assertReferencias(db)
        self.assertOriginalArchivado()

    def test_reemplazo_identico_no_borra(self):
        viejo, exp, archivos = self.anterior()
        db = SesionSimulada([viejo], exp)
        with self.assertRaises(HTTPException) as e:
            self.cargar(db, self.upload(Path(viejo.ruta).read_bytes()), reemplazar=True)
        self.assertEqual(e.exception.status_code, 409)
        self.assertConservados(archivos)
        self.assertEqual(db.mutaciones, 0)

    def test_parte_duplicada_sin_reemplazo_no_crea_operacion(self):
        viejo, exp, archivos = self.anterior()
        viejo.fragmento = 1
        db = SesionSimulada([viejo], exp)
        with self.assertRaises(HTTPException) as e:
            self.cargar(db, self.upload(nombre="CARPETA_00374-1.pdf"))
        self.assertEqual(e.exception.status_code, 409)
        self.assertEqual(self.diarios(), [])
        self.assertConservados(archivos)

    def test_reemplazo_de_parte_conserva_otras(self):
        viejo, exp, archivos = self.anterior()
        viejo.fragmento = 1
        otra_ruta = self.almacen / "parte2.pdf"
        crear_pdf(otra_ruta, 1)
        otro = Archivo(id=11, codigo_carpeta="AC-CP-00374", fragmento=2, ruta=str(otra_ruta),
                       sha256=sha(otra_ruta), tamano_bytes=otra_ruta.stat().st_size)
        db = SesionSimulada([viejo, otro], exp)
        self.cargar(db, self.upload(nombre="CARPETA_00374-1.pdf"), reemplazar=True)
        self.assertIn(otro, db.filas[Archivo])
        self.assertEqual(sorted(a.fragmento for a in db.filas[Archivo]), [1, 2])
        self.assertConservados(archivos)
        self.assertReferencias(db)

    def test_error_diario_antes_commit_impide_confirmacion(self):
        clase = self.codigo["_OperacionCargue"]
        real = clase.estado
        def estado(op, nombre, **cambios):
            if nombre == "confirmacion_sql_pendiente":
                raise OSError("synthetic journal failure")
            return real(op, nombre, **cambios)
        db = SesionSimulada()
        with patch.object(clase, "estado", new=estado), self.assertRaises(HTTPException):
            self.cargar(db)
        self.assertEqual(db.commit_calls, 0)
        self.assertEqual(db.filas[Archivo], [])
        self.assertFalse(self.diarios()[0]["commit_intentado"])
        self.assertOriginalArchivado()

    def test_error_diario_despues_commit_no_elimina_archivos(self):
        clase = self.codigo["_OperacionCargue"]
        real = clase.estado
        def estado(op, nombre, **cambios):
            if nombre == "confirmada":
                raise OSError("synthetic journal failure after commit")
            return real(op, nombre, **cambios)
        db = SesionSimulada()
        with patch.object(clase, "estado", new=estado), self.assertLogs("test.integridad", logging.ERROR):
            r = self.cargar(db)
        self.assertTrue(r["aviso_integridad"])
        self.assertReferencias(db)
        self.assertOriginalArchivado()
        self.assertEqual(self.diarios()[0]["estado"], "confirmacion_sql_pendiente")

    def test_pdf_corrupto_conservado_sin_registros(self):
        db = SesionSimulada()
        with self.assertRaises(HTTPException) as e:
            self.cargar(db, self.upload(b"not a PDF"))
        self.assertEqual(e.exception.status_code, 422)
        self.assertEqual(db.mutaciones, 0)
        p = next(self.almacen.glob("operaciones/*/original.pdf"))
        self.assertEqual(p.read_bytes(), b"not a PDF")

    def test_manifiesto_ata_original_partes_y_filas(self):
        db = SesionSimulada()
        self.cargar(db)
        diario = self.diarios()[0]
        self.assertEqual(diario["original"]["sha256"], self.nuevo_sha)
        self.assertTrue(diario["sql_confirmado"])
        self.assertEqual({a["id"] for a in diario["registros"]}, {a.id for a in db.filas[Archivo]})
        self.assertTrue(all(sha(a["ruta"]) == a["sha256"] for a in diario["registros"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
