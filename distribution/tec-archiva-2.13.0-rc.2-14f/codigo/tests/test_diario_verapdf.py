"""Regresión 10B: XML, hash, asociación y lectura de diarios antiguos sin cambios."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from geology.dominio import pdfa_controlado as p

XML = ('<?xml version="1.0"?><root><validationReport isCompliant="true" '
       'profileName="PDF/A-1b validation profile"><details failedRules="0" '
       'failedChecks="0"/></validationReport></root>')


class DiarioVeraPDF(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='geology10b-journal-'))
        self.pdf = self.base/'derivado.pdf'
        self.pdf.write_bytes(b'SINTETICO PARA PRUEBA DE ASOCIACION')
        self.xml = self.base/'verapdf.xml'

    def validar(self, informe=True):
        with patch('geology.dominio.validador_pdfa.binario', return_value='verapdf'), \
             patch.object(p, '_ejecutar', return_value=XML):
            return p.validar(self.pdf, '1b', informe=self.xml if informe else None)

    def diario(self, legado=False):
        resultado = self.validar()
        if legado:
            resultado['informe'] = "<Element 'validationReport' at 0x000001>"
            resultado.pop('archivo_validado_sha256')
        return p.evento(self.base, 'validado_publicado', **resultado,
                        ruta=str(self.pdf), sha256=p.huella(self.pdf))

    def test_regresion_ruta_no_se_sustituye_por_elemento_xml(self):
        r = self.validar()
        self.assertEqual(r['informe'], str(self.xml))
        self.assertTrue(Path(r['informe']).is_file())
        self.assertEqual(r['informe_sha256'], p.huella(self.xml))
        self.assertEqual(r['archivo_validado_sha256'], p.huella(self.pdf))

    def test_sin_archivo_informe_no_inventa_ruta(self):
        self.assertIsNone(self.validar(False)['informe'])
        self.assertFalse(self.xml.exists())

    def test_informe_previo_no_se_sobrescribe(self):
        self.xml.write_text('INFORME PREVIO')
        with self.assertRaises(FileExistsError):
            self.validar()
        self.assertEqual(self.xml.read_text(), 'INFORME PREVIO')

    def test_diario_nuevo_verificable(self):
        ruta = self.diario()
        sha = p.huella(ruta)
        r = p.verificar_diario(ruta)
        self.assertTrue(r['verificado'])
        self.assertFalse(r['referencia_historica_recuperada'])
        self.assertEqual(p.huella(ruta), sha)

    def test_diario_historico_recuperable_sin_modificarlo(self):
        ruta = self.diario(True)
        antes = {x.name: p.huella(x) for x in self.base.iterdir()}
        r = p.verificar_diario(ruta)
        self.assertTrue(r['referencia_historica_recuperada'])
        self.assertEqual(r['informe'], str(self.xml))
        self.assertEqual(antes, {x.name: p.huella(x) for x in self.base.iterdir()})

    def test_xml_alterado_requiere_revision(self):
        ruta = self.diario(True)
        self.xml.write_text(XML+'<!-- alteracion sintetica -->', encoding='utf-8')
        with self.assertRaises(p.ErrorPDFa):
            p.verificar_diario(ruta)

    def test_pdf_alterado_requiere_revision(self):
        ruta = self.diario()
        self.pdf.write_bytes(b'OTRO DERIVADO SINTETICO')
        with self.assertRaises(p.ErrorPDFa):
            p.verificar_diario(ruta)

    def test_no_busca_xml_ausente_en_otras_operaciones(self):
        ruta = self.diario(True)
        otro = self.base/'otro-intento'; otro.mkdir()
        copia = otro/'evento.json'; copia.write_bytes(ruta.read_bytes())
        with self.assertRaises(p.ErrorPDFa):
            p.verificar_diario(copia)

    def test_referencia_ajena_no_se_acepta(self):
        ruta = self.diario()
        datos = json.loads(ruta.read_text()); datos['informe'] = str(self.base/'ajeno.xml')
        nuevo = self.base/'evento-alterado.json'; nuevo.write_text(json.dumps(datos))
        with self.assertRaises(p.ErrorPDFa):
            p.verificar_diario(nuevo)

    def test_commit_incierto_no_se_interpreta_como_validacion(self):
        ruta = p.evento(self.base, 'commit_pendiente_conciliar_si_interrumpido')
        with self.assertRaises(p.ErrorPDFa):
            p.verificar_diario(ruta)

    def test_hash_de_asociacion_pdf_incorrecto_no_se_acepta(self):
        ruta = self.diario()
        datos = json.loads(ruta.read_text()); datos['archivo_validado_sha256'] = '0'*64
        nuevo = self.base/'evento-asociacion-invalida.json'; nuevo.write_text(json.dumps(datos))
        with self.assertRaises(p.ErrorPDFa):
            p.verificar_diario(nuevo)


if __name__ == '__main__':
    unittest.main()
