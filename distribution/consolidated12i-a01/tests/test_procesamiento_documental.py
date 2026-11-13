"""Documentos exclusivamente sintéticos; sin DB, colas ni proveedores externos."""
from __future__ import annotations

import ast
import copy
import hashlib
import io
import os
from pathlib import Path
import random
import socket
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import openpyxl
import pikepdf

from geology.dominio import division, hojas_calculo, particion


def sha(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def crear_pdf(ruta, paginas=5, peso=0, cifrado=None):
    """Páginas distinguibles y una imagen sintética por página, sin documentos reales."""
    with pikepdf.Pdf.new() as pdf:
        for i in range(1, paginas + 1):
            pagina = pdf.add_blank_page(page_size=(100 + i, 200 + i))
            n = peso[i - 1] if isinstance(peso, list) else peso
            carga = random.Random(i).randbytes(n).hex().encode()
            imagen = pikepdf.Stream(pdf, bytes((i + j) % 256 for j in range(64)))
            imagen.Type = pikepdf.Name.XObject
            imagen.Subtype = pikepdf.Name.Image
            imagen.Width, imagen.Height = 8, 8
            imagen.ColorSpace = pikepdf.Name.DeviceGray
            imagen.BitsPerComponent = 8
            pagina.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=imagen))
            pagina.Contents = pikepdf.Stream(pdf, b"q 8 0 0 8 0 0 cm /Im0 Do Q\n%PAGINA:" + str(i).encode() + b"\n%" + carga + b"\n")
        opciones = {"compress_streams": False}
        if cifrado:
            opciones["encryption"] = pikepdf.Encryption(owner="synthetic-owner", user=cifrado[0], R=6)
        pdf.save(ruta, **opciones)


def firmas(origen):
    objeto = io.BytesIO(origen) if isinstance(origen, bytes) else origen
    with pikepdf.open(objeto) as pdf:
        return [(tuple(p.MediaBox), p.Contents.read_bytes(), p.Resources.XObject.Im0.read_bytes()) for p in pdf.pages]


class Documentos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guardias = [patch.object(socket.socket, "connect", side_effect=AssertionError("Red prohibida")), patch("socket.create_connection", side_effect=AssertionError("Red prohibida"))]
        cls.espias = [g.start() for g in cls.guardias]

    @classmethod
    def tearDownClass(cls):
        for e in cls.espias:
            e.assert_not_called()
        for g in reversed(cls.guardias):
            g.stop()

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="geology-synthetic-")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.destino = self.raiz / "partes"
        self.destino.mkdir()
        self.origen = self.raiz / "origen.pdf"
        crear_pdf(self.origen)
        self.original_sha = sha(self.origen)
        self.limite = patch.object(division, "PAGINAS_POR_PARTE", 2)
        self.limite.start()
        self.addCleanup(self.limite.stop)

    def dividir(self, **cambios):
        args = dict(origen=self.origen, carpeta="AC-CP-00374", destino=self.destino, nombre="CARPETA_00374.pdf")
        args.update(cambios)
        return division.dividir(**args)

    def assertOriginal(self):
        self.assertTrue(self.origen.is_file())
        self.assertEqual(sha(self.origen), self.original_sha)

    def test_division_una_pagina_no_divide(self):
        crear_pdf(self.origen, 1)
        antes = sha(self.origen)
        self.assertEqual(self.dividir(), [])
        self.assertEqual(sha(self.origen), antes)
        self.assertEqual(list(self.destino.iterdir()), [])

    def test_division_orden_imagenes_y_hashes(self):
        originales = firmas(self.origen)
        partes = self.dividir()
        self.assertEqual([(p.pagina_inicial, p.pagina_final, p.paginas) for p in partes], [(1, 2, 2), (3, 4, 2), (5, 5, 1)])
        unidas = []
        for n, p in enumerate(partes, 1):
            self.assertEqual(p.numero, n)
            self.assertEqual(p.sha256, sha(p.ruta))
            self.assertEqual(p.tamano_bytes, p.ruta.stat().st_size)
            unidas.extend(firmas(p.ruta))
        self.assertEqual(unidas, originales)
        self.assertOriginal()
        self.assertEqual(len(list(self.destino.iterdir())), 3)

    def test_division_limite_exacto_y_cero(self):
        self.assertFalse(division.hay_que_dividir(2))
        self.assertTrue(division.hay_que_dividir(3))
        with patch.object(division, "PAGINAS_POR_PARTE", 0):
            self.assertFalse(division.hay_que_dividir(500))
            self.assertEqual(self.dividir(), [])
        self.assertOriginal()

    def test_division_configuracion_invalida(self):
        for valor in ("-1", "abc"):
            with self.subTest(valor=valor), patch.dict(os.environ, {"PAGINAS_POR_PARTE": valor}):
                with self.assertRaises(ValueError):
                    division._limite_configurado()

    def test_division_paginas_invalidas(self):
        for valor in (-1, True, 1.5, "2"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                division.hay_que_dividir(valor)

    def test_division_reintento_no_sobrescribe(self):
        partes = self.dividir()
        antes = {p.ruta.name: sha(p.ruta) for p in partes}
        with self.assertRaises(FileExistsError):
            self.dividir()
        self.assertEqual({p.name: sha(p) for p in self.destino.iterdir()}, antes)
        self.assertOriginal()

    def test_division_error_escritura_limpia_temporales(self):
        real = division._guardar_pdf
        contador = 0
        def escribir(pdf, ruta):
            nonlocal contador
            contador += 1
            if contador == 2:
                ruta.write_bytes(b"partial-synthetic")
                raise OSError("synthetic disk full")
            return real(pdf, ruta)
        with patch.object(division, "_guardar_pdf", side_effect=escribir), self.assertRaises(OSError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertOriginal()

    def test_division_error_publicacion_revierte_lote(self):
        real = division._publicar_atomico
        contador = 0
        def publicar(temporal, destino):
            nonlocal contador
            contador += 1
            if contador == 2:
                raise OSError("synthetic publication failure")
            real(temporal, destino)
        with patch.object(division, "_publicar_atomico", side_effect=publicar), self.assertRaises(OSError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertOriginal()

    def test_division_colision_concurrente_preserva_ajeno(self):
        real = division._publicar_atomico
        contador = 0
        ajenos = []
        def publicar(temporal, destino):
            nonlocal contador
            contador += 1
            if contador == 2:
                destino.write_bytes(b"foreign-synthetic")
                ajenos.append(destino)
            real(temporal, destino)
        with patch.object(division, "_publicar_atomico", side_effect=publicar), self.assertRaises(FileExistsError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), ajenos)
        self.assertEqual(ajenos[0].read_bytes(), b"foreign-synthetic")
        self.assertOriginal()

    def test_division_filesystem_sin_enlaces_falla_seguro(self):
        with patch.object(division.os, "link", side_effect=OSError("hard links unavailable")), self.assertRaises(OSError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertOriginal()

    def test_division_error_fsync_no_publica(self):
        with patch.object(division.os, "fsync", side_effect=OSError("synthetic flush failure")), self.assertRaises(OSError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertOriginal()

    def test_division_origen_cambia_no_publica(self):
        # Simula detección de cambio sin modificar el archivo fuente real.
        real = division._huella
        llamadas = 0
        def huella(p):
            nonlocal llamadas
            if p == self.origen:
                llamadas += 1
                if llamadas == 2:
                    return "0" * 64
            return real(p)
        with patch.object(division, "_huella", side_effect=huella), self.assertRaises(RuntimeError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertOriginal()

    def test_division_nombres_inseguros(self):
        for nombre in ("../escape.pdf", "..\\escape.pdf", "/absolute.pdf", "a/b.pdf", "a\\b.pdf", "a:b.pdf", "NUL.pdf", "COM1.pdf", ".hidden", "a..pdf", "a.pdf.", "", "x" * 121):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                self.dividir(nombre=nombre)
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertOriginal()

    def test_division_codigo_inseguro(self):
        for codigo in ("../x", "carpeta", "AC-CP-1", "AC-CP-１２３４５"):
            with self.subTest(codigo=codigo), self.assertRaises(ValueError):
                self.dividir(carpeta=codigo)

    def test_division_codigo_seis_digitos(self):
        partes = self.dividir(carpeta="AC-CP-123456")
        self.assertEqual(len(partes), 3)
        self.assertTrue(partes[0].ruta.name.startswith("AC-CP-123456_"))

    def test_division_destino_no_directorio_o_retroceso(self):
        for destino in (self.origen, self.destino / ".."):
            with self.subTest(destino=str(destino)), self.assertRaises(ValueError):
                self.dividir(destino=destino)
        with self.assertRaises(FileNotFoundError):
            self.dividir(destino=self.raiz / "missing")
        self.assertOriginal()

    def test_division_rechaza_symlinks(self):
        enlace = self.raiz / "link-dir"
        enlace.symlink_to(self.destino, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.dividir(destino=enlace)
        fuente = self.raiz / "link.pdf"
        fuente.symlink_to(self.origen)
        with self.assertRaises(particion.DocumentoIlegible):
            self.dividir(origen=fuente)
        self.assertOriginal()

    def test_division_pdf_corrupto_sin_residuos(self):
        malo = self.raiz / "corrupt.pdf"
        malo.write_bytes(b"not a PDF")
        antes = sha(malo)
        with self.assertRaises(particion.DocumentoIlegible):
            self.dividir(origen=malo)
        self.assertEqual(sha(malo), antes)
        self.assertEqual(list(self.destino.iterdir()), [])

    def test_division_pdf_cifrado_no_se_descifra(self):
        cifrado = self.raiz / "encrypted.pdf"
        crear_pdf(cifrado, cifrado=("synthetic-reader",))
        antes = sha(cifrado)
        with self.assertRaises(particion.DocumentoIlegible):
            self.dividir(origen=cifrado)
        self.assertEqual(sha(cifrado), antes)
        self.assertEqual(list(self.destino.iterdir()), [])

    def test_division_tope_tecnico_no_publica(self):
        with patch.object(division, "_MAX_PARTES", 1), self.assertRaises(ValueError):
            self.dividir()
        self.assertEqual(list(self.destino.iterdir()), [])

    def test_secuencias_vacias_enteras_y_huecos(self):
        for entrada, esperado in [([], []), ([0], []), ([1], []), ([3, 1, 1], [2]), ([2, 4], [1, 3]), ([0, 1, 3], [2])]:
            with self.subTest(entrada=entrada):
                self.assertEqual(division.faltantes(entrada), esperado)
        self.assertIn("Sin archivos", division.describir_secuencia([]))
        self.assertIn("completo", division.describir_secuencia([0]))
        self.assertIn("Faltan las partes 2", division.describir_secuencia([3, 1]))
        self.assertIn("modalidad", division.describir_secuencia([0, 1]))

    def test_secuencia_no_asume_ultima_parte(self):
        self.assertEqual(division.faltantes([1, 2]), [])
        for valor in (-1, None, True, "2", 10**12):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                division.faltantes([valor])

    def test_particion_una_pagina(self):
        crear_pdf(self.origen, 1)
        antes = sha(self.origen)
        bloques = list(particion.bloques(self.origen, 10, 1, []))
        self.assertEqual(len(bloques), 1)
        self.assertEqual((bloques[0].numero, bloques[0].pagina_inicial, bloques[0].pagina_final), (1, 1, 1))
        self.assertIsInstance(bloques[0].contenido, bytes)
        self.assertEqual(firmas(bloques[0].contenido), firmas(self.origen))
        self.assertEqual(sha(self.origen), antes)

    def test_particion_paginas_orden_y_original(self):
        bloques = list(particion.bloques(self.origen, 2, 1, []))
        self.assertEqual([(b.pagina_inicial, b.pagina_final) for b in bloques], [(1, 2), (3, 4), (5, 5)])
        self.assertEqual([b.numero for b in bloques], [1, 2, 3])
        self.assertEqual([p for b in bloques for p in firmas(b.contenido)], firmas(self.origen))
        self.assertOriginal()

    def test_particion_limite_binario(self):
        crear_pdf(self.origen, peso=5000)
        antes = sha(self.origen)
        bloques = list(particion.bloques(self.origen, 5, 18000 / 1048576, []))
        self.assertEqual(len(bloques), 5)
        self.assertTrue(all(len(b.contenido) <= 18000 for b in bloques))
        self.assertEqual([p for b in bloques for p in firmas(b.contenido)], firmas(self.origen))
        self.assertEqual(sha(self.origen), antes)

    def test_particion_limite_exacto_y_un_byte_menos(self):
        crear_pdf(self.origen, 1, peso=1000)
        primero = list(particion.bloques(self.origen, 1, 1, []))[0]
        limite = len(primero.contenido)
        self.assertEqual(len(list(particion.bloques(self.origen, 1, limite / 1048576, []))[0].contenido), limite)
        avisos = []
        with self.assertRaises(particion.DocumentoIlegible):
            list(particion.bloques(self.origen, 1, (limite - 1) / 1048576, avisos))
        self.assertTrue(avisos)

    def test_particion_pagina_grande_no_vulnera_tope(self):
        crear_pdf(self.origen, 2, peso=[0, 10000])
        antes = sha(self.origen)
        avisos = []
        generador = particion.bloques(self.origen, 2, 5000 / 1048576, avisos)
        primero = next(generador)
        self.assertEqual((primero.pagina_inicial, primero.pagina_final), (1, 1))
        self.assertLessEqual(len(primero.contenido), 5000)
        with self.assertRaises(particion.DocumentoIlegible):
            next(generador)
        self.assertIn("página 2", avisos[-1])
        self.assertEqual(sha(self.origen), antes)

    def test_particion_parametros_invalidos(self):
        for paginas in (0, -1, True, 2.5, "2"):
            with self.subTest(paginas=paginas), self.assertRaises(ValueError):
                particion.bloques(self.origen, paginas, 1, [])
        for mb in (0, -1, True, float("nan"), float("inf"), "1", 0.00000001, 1e308, 10**400):
            with self.subTest(mb=mb), self.assertRaises(ValueError):
                particion.bloques(self.origen, 1, mb, [])
        with self.assertRaises(TypeError):
            particion.bloques(self.origen, 1, 1, None)

    def test_particion_contar_y_archivo_ausente(self):
        self.assertEqual(particion.contar_paginas(self.origen), 5)
        for ruta in (self.raiz / "absent.pdf", self.destino):
            with self.subTest(ruta=str(ruta)), self.assertRaises(particion.DocumentoIlegible):
                particion.contar_paginas(ruta)
        self.assertOriginal()

    def test_particion_corrupto(self):
        malo = self.raiz / "bad.pdf"
        malo.write_bytes(b"%PDF-1.7\ninvalid structure")
        antes = sha(malo)
        for operacion in (lambda: particion.contar_paginas(malo), lambda: list(particion.bloques(malo, 2, 1, []))):
            with self.assertRaises(particion.DocumentoIlegible):
                operacion()
        self.assertEqual(sha(malo), antes)

    def test_particion_cifrado_con_password_y_vacio(self):
        for clave in ("synthetic-reader", ""):
            ruta = self.raiz / ("protected.pdf" if clave else "empty-password.pdf")
            crear_pdf(ruta, cifrado=(clave,))
            antes = sha(ruta)
            with self.assertRaises(particion.DocumentoIlegible):
                particion.contar_paginas(ruta)
            with self.assertRaises(particion.DocumentoIlegible):
                list(particion.bloques(ruta, 2, 1, []))
            self.assertEqual(sha(ruta), antes)

    def test_particion_pdf_sin_paginas(self):
        vacio = self.raiz / "empty.pdf"
        crear_pdf(vacio, 0)
        with self.assertRaises(particion.DocumentoIlegible):
            particion.contar_paginas(vacio)

    def test_particion_error_durante_lectura_preserva_original(self):
        with patch.object(particion, "_serializar", side_effect=pikepdf.PdfError("synthetic parse failure")):
            with self.assertRaises(particion.DocumentoIlegible):
                list(particion.bloques(self.origen, 2, 1, []))
        self.assertOriginal()

    def test_particion_cierre_anticipado(self):
        bloques = particion.bloques(self.origen, 1, 1, [])
        next(bloques)
        bloques.close()
        self.assertEqual(bloques.gi_frame, None)
        self.assertOriginal()

    def test_integracion_contrato_campos_cargue(self):
        for p in self.dividir():
            # Campos efectivamente usados al construir Archivo en cargue.py.
            payload = dict(fragmento=p.numero, ruta=str(p.ruta), tamano_bytes=p.tamano_bytes,
                           sha256=p.sha256, paginas=p.paginas, pagina_inicial=p.pagina_inicial,
                           pagina_final=p.pagina_final)
            self.assertEqual(payload["paginas"], payload["pagina_final"] - payload["pagina_inicial"] + 1)
            self.assertEqual(payload["sha256"], sha(payload["ruta"]))
        self.assertOriginal()

    def test_integracion_adaptador_real_trabajos(self):
        # Extrae solo el adaptador existente: no importa trabajos ni registra tareas.
        ruta = Path(division.__file__).parents[1] / "trabajos" / "__init__.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))
        funcion = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "_uno_a_uno")
        espacio = {}
        exec(compile(ast.Module(body=[funcion], type_ignores=[]), str(ruta), "exec"), espacio)
        crear_pdf(self.origen, 2, peso=[0, 10000])
        avisos = []
        salida = list(espacio["_uno_a_uno"](particion.bloques(self.origen, 2, 5000 / 1048576, avisos), "synthetic.pdf", avisos))
        self.assertEqual(len(salida), 1)
        self.assertEqual(salida[0].pagina_final, 1)
        self.assertTrue(any("se detuvo" in a for a in avisos))

    def test_integracion_cargue_no_borra_fuente(self):
        ruta = Path(division.__file__).parents[1] / "rutas" / "cargue.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))
        llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)]
        self.assertFalse(any(ast.unparse(n.func) == "destino.unlink" for n in llamadas))
        # El consumidor original no se ejecuta ni modifica en esta prueba.
        self.assertOriginal()


class Excel(unittest.TestCase):
    def libro(self, filas, columnas):
        contenido = hojas_calculo.generar_base_isadg(filas, columnas)
        self.assertIsInstance(contenido, bytes)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(contenido)))
        return openpyxl.load_workbook(io.BytesIO(contenido)), contenido

    def test_excel_orden_nulos_y_caracteres(self):
        filas = [{"B": "Bogotá ñ & < > \" ' 😀\nsegunda línea", "A": None}]
        libro, _ = self.libro(filas, [("2", "B"), ("1", "A")])
        self.addCleanup(libro.close)
        self.assertEqual(list(libro.active.values), [("2", "1"), ("B", "A"), (filas[0]["B"], None)])

    def test_excel_formulas_son_texto_literal(self):
        valores = ["=1+1", "+SUM(A1:A2)", "-1+2", "@SUM(A1)", "\t=1+1", " =1+1", "\n@x", "#N/A"]
        libro, contenido = self.libro([{"Valor": v} for v in valores], [("=numeral", "Valor")])
        self.addCleanup(libro.close)
        for i, valor in enumerate(valores, 3):
            self.assertEqual(libro.active.cell(i, 1).value, valor)
            self.assertEqual(libro.active.cell(i, 1).data_type, "s")
        self.assertEqual(libro.active.cell(1, 1).data_type, "s")
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            self.assertNotIn(b"<f>", z.read("xl/worksheets/sheet1.xml"))

    def test_excel_no_muta_entradas(self):
        filas = [{"A": "=1+1", "extra": [1, 2]}, {"A": None}]
        columnas = [["1", "A"]]
        copia_filas, copia_columnas = copy.deepcopy(filas), copy.deepcopy(columnas)
        hojas_calculo.generar_base_isadg(filas, columnas)
        self.assertEqual(filas, copia_filas)
        self.assertEqual(columnas, copia_columnas)

    def test_excel_vacio_con_cabeceras(self):
        libro, _ = self.libro([], [("1", "A")])
        self.addCleanup(libro.close)
        self.assertEqual(libro.active.max_row, 2)

    def test_excel_tipos_numericos_y_fechas(self):
        from datetime import datetime
        from decimal import Decimal
        valores = [-42, 3.5, True, Decimal("2.25"), datetime(2026, 1, 2)]
        libro, _ = self.libro([{"A": v} for v in valores], [("1", "A")])
        self.addCleanup(libro.close)
        self.assertEqual([libro.active.cell(i, 1).value for i in range(3, 8)], [-42, 3.5, True, 2.25, datetime(2026, 1, 2)])

    def test_excel_rechaza_perdida_de_texto(self):
        for valor in ("bad\x00text", "x" * 32768):
            with self.subTest(largo=len(valor)), self.assertRaises(ValueError):
                hojas_calculo.generar_base_isadg([{"A": valor}], [("1", "A")])

    def test_excel_rechaza_columnas_y_filas_invalidas(self):
        for columnas in ([], ["A"], [("1", "")], [(1, "A")]):
            with self.subTest(columnas=columnas), self.assertRaises(ValueError):
                hojas_calculo.generar_base_isadg([], columnas)
        with self.assertRaises(TypeError):
            hojas_calculo.generar_base_isadg([None], [("1", "A")])

    def test_excel_rechaza_valores_no_representables(self):
        from datetime import datetime, timezone
        for valor in (float("nan"), float("inf"), datetime(2026, 1, 1, tzinfo=timezone.utc)):
            with self.subTest(tipo=type(valor).__name__), self.assertRaises(ValueError):
                hojas_calculo.generar_base_isadg([{"A": valor}], [("1", "A")])
        with self.assertRaises(TypeError):
            hojas_calculo.generar_base_isadg([{"A": object()}], [("1", "A")])

    def test_excel_error_escritura_no_muta(self):
        filas = [{"A": "texto"}]
        with patch.object(hojas_calculo.Workbook, "save", side_effect=OSError("synthetic write failure")), self.assertRaises(OSError):
            hojas_calculo.generar_base_isadg(filas, [("1", "A")])
        self.assertEqual(filas, [{"A": "texto"}])

    def test_excel_columnas_reales_y_respuesta_fastapi(self):
        ruta = Path(division.__file__).parents[1] / "rutas" / "instrumentos.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))
        nodo = next(n for n in arbol.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COLUMNAS_ISADG" for t in n.targets))
        columnas = ast.literal_eval(nodo.value)
        filas = [{etiqueta: "valor " + str(i) for i, (_, etiqueta) in enumerate(columnas)}]
        libro, contenido = self.libro(filas, columnas)
        self.addCleanup(libro.close)
        self.assertEqual([c.value for c in libro.active[2]], [c[1] for c in columnas])
        self.assertEqual([c.value for c in libro.active[3]], [filas[0][c[1]] for c in columnas])
        from fastapi.responses import Response
        respuesta = Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertEqual(respuesta.body, contenido)


if __name__ == "__main__":
    unittest.main(verbosity=2)
