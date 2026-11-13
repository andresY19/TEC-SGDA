"""Ejecutar sólo en contenedor sin red y con directorio sintético propio.

Herramientas reales OCRmyPDF/Ghostscript/pikepdf/veraPDF. Persistencia simulada:
no se abre PostgreSQL ni Redis, ni se publica ninguna tarea Celery.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pikepdf
from geology.dominio import pdfa_controlado as p

BASE = Path('/work/results/integration')


def crear(ruta, paginas):
    with pikepdf.Pdf.new() as pdf:
        for i in range(paginas):
            page = pdf.add_blank_page(page_size=(300, 400))
            font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                      BaseFont=pikepdf.Name.Helvetica)
            page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            page.Contents = pikepdf.Stream(pdf, (
                f'BT /F1 14 Tf 30 200 Td (SINTETICO 10A PAGINA {i+1} DE {paginas}) Tj ET').encode())
        pdf.save(ruta)


class PDFaReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.mkdir(parents=True, exist_ok=False)
        cls.results = []
        cls.originals = {}
        for n in (1, 3):
            ruta = BASE / f'SINTETICO-{n}.pdf'
            crear(ruta, n)
            cls.originals[str(ruta)] = p.huella(ruta)
        cls.old = BASE / 'derivado-anterior.pdf'
        cls.old.write_bytes(b'SINTETICO ANTERIOR NO MODIFICAR')
        cls.old_sha = p.huella(cls.old)

    @classmethod
    def tearDownClass(cls):
        assert all(p.huella(Path(r)) == sha for r, sha in cls.originals.items())
        assert p.huella(cls.old) == cls.old_sha
        (BASE/'certificacion.json').write_text(json.dumps({
            'resultados': cls.results, 'originales': cls.originals,
            'derivado_previo_sha256': cls.old_sha, 'originales_conservados': True,
            'derivado_previo_conservado': True}, indent=2), encoding='utf-8')

    def certificar(self, perfil, paginas, consulta=False):
        src = BASE/f'SINTETICO-{paginas}.pdf'
        dst = BASE/f'nuevo-{perfil}-{paginas}-{consulta}.pdf'
        resultado = p.convertir(src, dst, perfil=perfil, consulta=consulta, con_ocr=False)
        # Nueva ejecución independiente sobre el archivo publicado, sin cache.
        resultado['segunda_validacion'] = p.validar(dst, perfil)
        self.assertEqual(p.contenido(src), p.contenido(dst))
        self.assertEqual(resultado['sha256'], p.huella(dst))
        self.verificar_informe(resultado)
        self.results.append(resultado)

    def verificar_informe(self, resultado):
        xml = Path(resultado['informe'])
        self.assertTrue(xml.is_file())
        self.assertEqual(p.huella(xml), resultado['informe_sha256'])
        self.assertEqual(resultado['archivo_validado_sha256'], resultado['sha256'])
        eventos = [x for x in xml.parent.glob('evento-*.json')
                   if json.loads(x.read_text())['estado'] == 'validado_publicado']
        self.assertEqual(len(eventos), 1)
        verificacion = p.verificar_diario(eventos[0])
        self.assertTrue(verificacion['verificado'])
        self.assertFalse(verificacion['diario_modificado'])

    def test_01_pdfa_1b_one_page(self):
        self.certificar('1b', 1)

    def test_02_pdfa_2b_one_page(self):
        self.certificar('2b', 1)

    def test_03_pdfa_1b_three_pages_matrix(self):
        self.certificar('1b', 3)

    def test_04_pdfa_2b_three_pages_matrix(self):
        self.certificar('2b', 3)

    def test_05_pdfa_1b_three_pages_consultation(self):
        self.certificar('1b', 3, True)

    def test_06_pdfa_2b_three_pages_consultation(self):
        self.certificar('2b', 3, True)

    def test_07_actual_celery_task_contract_without_broker(self):
        # La tarea real se invoca directamente. Ninguna publicación/consumo.
        from geology.trabajos import preparar_digitalizacion
        with patch('geology.trabajos.SesionLocal', side_effect=AssertionError('DB no permitida')):
            with self.assertRaises(p.ErrorPDFa):
                preparar_digitalizacion.run(1, perfil_solicitado='invalid')
        self.assertEqual(preparar_digitalizacion.name, 'geology.preparar_digitalizacion')

    def test_08_corrupt_real_pdf(self):
        src = BASE/'corrupto.pdf'; src.write_bytes(b'%PDF-invalid')
        with self.assertRaises(p.ErrorPDFa):
            p.convertir(src, BASE/'no-publicar.pdf', perfil='1b')
        self.assertEqual(src.read_bytes(), b'%PDF-invalid')

    def test_09_existing_derivative_never_overwritten(self):
        with self.assertRaises(p.ErrorPDFa):
            p.convertir(BASE/'SINTETICO-1.pdf', self.old, perfil='2b')
        self.assertEqual(p.huella(self.old), self.old_sha)

    def test_10_legacy_default_real_output_stays_2b(self):
        src, dst = BASE/'SINTETICO-1.pdf', BASE/'predeterminado.pdf'
        r = p.convertir(src, dst)
        self.assertEqual(r['perfil'], '2b')
        self.assertIsNone(r['perfil_solicitado'])
        r['segunda_validacion'] = p.validar(dst, '2b')
        self.verificar_informe(r)
        self.results.append(r)

    def task_verified(self, perfil):
        from geology.trabajos import preparar_digitalizacion
        row = SimpleNamespace(ruta=str(BASE/'SINTETICO-3.pdf'),
            ruta_matriz=str(self.old), ruta_consulta=str(self.old), ruta_texto=None,
            tiene_capa_de_texto=True, nombre_original='SINTETICO 10A')
        class Session:
            def get(self, *a, **kw): return row
            def close(self): pass
            def commit(self): pass
            def rollback(self): pass
        with patch('geology.trabajos.SesionLocal', Session):
            r = preparar_digitalizacion.run(99, perfil_solicitado=perfil)
        self.assertEqual(r['perfil'], perfil)
        self.assertEqual(r['problemas'], [])
        self.assertEqual(row.ruta, str(BASE/'SINTETICO-3.pdf'))
        for x in r['resultados']:
            x['segunda_validacion'] = p.validar(Path(x['ruta']), perfil)
            self.verificar_informe(x)
            self.results.append(x)

    def test_11_real_task_1b_without_broker_or_database(self):
        self.task_verified('1b')

    def test_12_real_task_2b_without_broker_or_database(self):
        self.task_verified('2b')

    def test_13_all_journals_bind_xml_and_published_derivative(self):
        resultados = []
        for ruta in BASE.rglob('evento-*.json'):
            if json.loads(ruta.read_text())['estado'] == 'validado_publicado':
                resultados.append(p.verificar_diario(ruta))
        self.assertEqual(len(resultados), 11)
        self.assertEqual({x['perfil'] for x in resultados}, {'1b', '2b'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
