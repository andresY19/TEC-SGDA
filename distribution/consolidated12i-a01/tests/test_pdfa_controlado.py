"""Pruebas sintéticas: no usan PostgreSQL, Redis ni documentos activos."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from geology.dominio import pdfa_controlado as p


class PDFaControlado(unittest.TestCase):
    def setUp(self):
        # Retenidos para revisión; no se elimina evidencia de la operación.
        self.base = Path(tempfile.mkdtemp(prefix="pdfa10a-unit-"))
        self.src = self.base / "original.pdf"
        self.src.write_bytes(b"synthetic original")
        self.out = self.base / "nuevo.pdf"

    def run_conversion(self, perfil="1b", runner=None):
        def ejecutar(args, timeout):
            Path(args[-1]).write_bytes(b"synthetic derivative")
            return ""
        with patch.object(p, "contenido", return_value=["uno", "dos"]), \
             patch.object(p, "validar", return_value={"conforme": True, "perfil": perfil}), \
             patch.object(p, "_ejecutar", side_effect=runner or ejecutar):
            return p.convertir(self.src, self.out, perfil=perfil)

    def test_profiles_and_legacy_default(self):
        self.assertEqual(p.perfil_efectivo(None), "2b")
        for x in ("1b", "2b"):
            self.assertEqual(p.perfil_efectivo(x), x)

    def test_invalid_profiles_have_no_effects(self):
        for x in ("", "1B", "pdfa-1", "3b", "../../1b", True, 1):
            with self.subTest(x=x), self.assertRaises(p.ErrorPDFa):
                p.convertir(self.src, self.out, perfil=x)
        self.assertEqual(list(self.base.iterdir()), [self.src])

    def test_success_hashes_original_and_output(self):
        sha = p.huella(self.src)
        r = self.run_conversion()
        self.assertEqual(r["sha256"], p.huella(self.out))
        self.assertEqual(r["origen_sha256"], sha)
        self.assertEqual(p.huella(self.src), sha)
        self.assertEqual(r["paginas"], 2)

    def test_collision_preserves_old_derivative(self):
        self.out.write_bytes(b"previous")
        with self.assertRaises(p.ErrorPDFa):
            self.run_conversion()
        self.assertEqual(self.out.read_bytes(), b"previous")

    def test_same_path_refused(self):
        with self.assertRaises(p.ErrorPDFa):
            p.convertir(self.src, self.src)

    def test_insufficient_space(self):
        with patch.object(p, "contenido", return_value=["uno"]), \
             patch.object(p.shutil, "disk_usage", return_value=SimpleNamespace(free=0)):
            with self.assertRaises(p.ErrorPDFa):
                p.convertir(self.src, self.out)
        self.assertFalse(self.out.exists())

    def test_ghostscript_chain_failure(self):
        with self.assertRaises(p.ErrorPDFa):
            self.run_conversion(runner=lambda *a: (_ for _ in ()).throw(p.ErrorPDFa("Ghostscript")))
        self.assertFalse(self.out.exists())

    def test_verapdf_failure_no_publication(self):
        def run(args, _):
            Path(args[-1]).write_bytes(b"partial")
            return ""
        with patch.object(p, "contenido", return_value=["uno"]), \
             patch.object(p, "_ejecutar", side_effect=run), \
             patch.object(p, "validar", side_effect=p.ErrorPDFa("invalid")):
            with self.assertRaises(p.ErrorPDFa):
                p.convertir(self.src, self.out)
        self.assertFalse(self.out.exists())
        self.assertTrue(list(self.base.glob(".pdfa-*/resultado.pdf")))

    def test_changed_page_order_fails(self):
        def run(args, _):
            Path(args[-1]).write_bytes(b"output")
            return ""
        with patch.object(p, "contenido", side_effect=[["uno", "dos"], ["dos", "uno"]]), \
             patch.object(p, "_ejecutar", side_effect=run), \
             patch.object(p, "validar", return_value={"conforme": True}):
            with self.assertRaises(p.ErrorPDFa):
                p.convertir(self.src, self.out)
        self.assertFalse(self.out.exists())

    def test_interruption_retains_original(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_conversion(runner=lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(self.src.read_bytes(), b"synthetic original")
        self.assertFalse(self.out.exists())

    def test_converter_commands_preserve_default(self):
        for perfil, esperado in ((None, "pdfa"), ("1b", "pdfa-1"), ("2b", "pdfa-2")):
            self.out = self.base / f"salida-{perfil}.pdf"
            def run(args, _):
                self.assertEqual(args[args.index("--output-type") + 1], esperado)
                Path(args[-1]).write_bytes(b"new")
                return ""
            self.run_conversion(perfil=perfil, runner=run)

    def test_verapdf_rejects_wrong_profile_and_bad_reports(self):
        for salida in ("invalid", '<?xml version="1.0"?><root/>',
                       '<?xml version="1.0"?><root><validationReport isCompliant="true" '
                       'profileName="PDF/A-2b validation profile"><details failedRules="0" '
                       'failedChecks="0"/></validationReport></root>'):
            with patch("geology.dominio.validador_pdfa.binario", return_value="veraPDF"), \
                 patch.object(p, "_ejecutar", return_value=salida):
                with self.assertRaises(p.ErrorPDFa):
                    p.validar(self.src, "1b")

    def test_invalid_task_profile_does_not_open_database(self):
        def no_db():
            self.fail("database accessed")
        with self.assertRaises(p.ErrorPDFa):
            p.preparar(1, no_db, perfil="bad")

    def fake_session(self, fail=None):
        old1, old2 = self.base / "old1.pdf", self.base / "old2.pdf"
        old1.write_bytes(b"old1"); old2.write_bytes(b"old2")
        row = SimpleNamespace(ruta=str(self.src), ruta_matriz=str(old1),
                              ruta_consulta=str(old2), ruta_texto=None,
                              nombre_original="SINTETICO", tiene_capa_de_texto=True)
        class Session:
            def __init__(inner):
                inner.rollback_called = inner.closed = False
            def get(inner, *args, **kwargs):
                return row
            def close(inner):
                inner.closed = True
            def commit(inner):
                if fail:
                    raise fail()
            def rollback(inner):
                inner.rollback_called = True
        sesiones = [Session(), Session()]
        def factory():
            return sesiones.pop(0)
        return row, factory, list(sesiones), (old1, old2)

    def fake_convert(self, origen, destino, **kw):
        destino.write_bytes(b"SINTETICO-" + destino.name.encode())
        return {"ruta": str(destino), "sha256": p.huella(destino), "ruta_texto": None,
                "perfil": p.perfil_efectivo(kw["perfil"]), "conforme": True}

    def test_sql_success_references_only_complete_verified_pair(self):
        row, factory, sessions, old = self.fake_session()
        with patch.object(p, "convertir", side_effect=self.fake_convert):
            r = p.preparar(1, factory, perfil="1b")
        self.assertEqual(r["problemas"], [])
        self.assertEqual(row.ruta, str(self.src))
        self.assertTrue(all(s.closed for s in sessions))
        self.assertEqual([x.read_bytes() for x in old], [b"old1", b"old2"])

    def test_sql_error_rolls_back_retains_all_files_and_journal(self):
        row, factory, sessions, old = self.fake_session(RuntimeError)
        with patch.object(p, "convertir", side_effect=self.fake_convert):
            with self.assertRaises(RuntimeError):
                p.preparar(1, factory, perfil="2b")
        self.assertTrue(sessions[1].rollback_called)
        self.assertTrue(all(s.closed for s in sessions))
        self.assertTrue(all(x.exists() for x in old))
        self.assertEqual(len(list(self.base.glob("preservacion/versiones/*/*.pdf"))), 2)
        events = [json.loads(x.read_text()) for x in self.base.glob("preservacion/versiones/*/evento-*.json")]
        self.assertIn("no_confirmado_requiere_conciliacion", [x["estado"] for x in events])

    def test_failed_second_conversion_never_updates_sql_references(self):
        row, factory, sessions, old = self.fake_session()
        def conv(src, dst, **kw):
            if kw.get("consulta"):
                raise p.ErrorPDFa("consulta failed")
            return self.fake_convert(src, dst, **kw)
        with patch.object(p, "convertir", side_effect=conv):
            with self.assertRaises(p.ErrorPDFa):
                p.preparar(1, factory)
        self.assertEqual(row.ruta_matriz, str(old[0]))
        self.assertEqual(row.ruta_consulta, str(old[1]))

    def test_corrupt_pdf(self):
        with self.assertRaises(p.ErrorPDFa):
            p.convertir(self.src, self.out, perfil="1b")

    def test_encrypted_pdf(self):
        import pikepdf
        src = self.base / "encrypted.pdf"
        with pikepdf.Pdf.new() as pdf:
            pdf.add_blank_page()
            pdf.save(src, encryption=pikepdf.Encryption(owner="synthetic-owner", user="synthetic-user"))
        sha = p.huella(src)
        with self.assertRaises(p.ErrorPDFa):
            p.convertir(src, self.out, perfil="1b")
        self.assertEqual(p.huella(src), sha)

    def test_sql_interruption_requires_reconciliation(self):
        row, factory, sessions, old = self.fake_session(KeyboardInterrupt)
        with patch.object(p, "convertir", side_effect=self.fake_convert):
            with self.assertRaises(KeyboardInterrupt):
                p.preparar(1, factory)
        self.assertTrue(sessions[1].rollback_called)
        self.assertTrue(all(x.exists() for x in old))
        events = [json.loads(x.read_text()) for x in self.base.glob("preservacion/versiones/*/evento-*.json")]
        self.assertIn("commit_pendiente_conciliar_si_interrumpido", [x["estado"] for x in events])

    def test_retry_uses_another_directory(self):
        row, factory, sessions, old = self.fake_session()
        with patch.object(p, "convertir", side_effect=self.fake_convert):
            first = p.preparar(1, factory)
        first_matrix = Path(first["matriz"])
        first_hash = p.huella(first_matrix)
        class Session:
            def get(self, *a, **kw): return row
            def close(self): pass
            def commit(self): pass
            def rollback(self): pass
        with patch.object(p, "convertir", side_effect=self.fake_convert):
            second = p.preparar(1, Session)
        self.assertNotEqual(first["matriz"], second["matriz"])
        self.assertEqual(p.huella(first_matrix), first_hash)

    def test_source_changed_during_conversion(self):
        def run(args, _):
            Path(args[-1]).write_bytes(b"new")
            self.src.write_bytes(b"changed-by-other-operation")
            return ""
        with self.assertRaises(p.ErrorPDFa):
            self.run_conversion(runner=run)
        self.assertFalse(self.out.exists())

    def test_external_errors_are_sanitized(self):
        with patch.object(p.subprocess, "run", return_value=SimpleNamespace(
                returncode=1, stdout="", stderr="private-secret-or-document-text")):
            with self.assertRaises(p.ErrorPDFa) as ctx:
                p._ejecutar(["gs"], 1)
        self.assertNotIn("private", str(ctx.exception))

    def test_write_error_preserves_original(self):
        with patch.object(p.os, "link", side_effect=OSError("write failure")):
            with self.assertRaises(OSError):
                self.run_conversion()
        self.assertFalse(self.out.exists())
        self.assertEqual(self.src.read_bytes(), b"synthetic original")

    def test_low_level_contracts_and_existing_sidecar(self):
        from geology.dominio.recepcion_tecnica import matriz_de_preservacion, copia_de_consulta
        with patch.object(p, "convertir", return_value={"ruta_texto": None}) as convertir:
            self.assertEqual(matriz_de_preservacion(self.src, self.out), (True, ""))
            self.assertIsNone(convertir.call_args.kwargs["perfil"])
            self.assertEqual(copia_de_consulta(self.src, self.out, False, perfil="2b"), (True, ""))
        self.out.with_suffix(".txt").write_text("previous")
        self.assertFalse(copia_de_consulta(self.src, self.out, True, perfil="1b")[0])
        self.assertEqual(self.out.with_suffix(".txt").read_text(), "previous")

    def test_stored_source_hash_mismatch_prevents_conversion(self):
        row, factory, sessions, old = self.fake_session()
        row.sha256 = '0' * 64
        with patch.object(p, "convertir") as convertir:
            with self.assertRaises(p.ErrorPDFa):
                p.preparar(1, factory)
            convertir.assert_not_called()
        self.assertTrue(all(x.exists() for x in old))

    def test_concurrent_reference_change_is_not_replaced(self):
        row, factory, sessions, old = self.fake_session()
        other = self.base/'concurrent.pdf'; other.write_bytes(b'other operation')
        def conv(src, dst, **kw):
            r = self.fake_convert(src, dst, **kw)
            if kw.get('consulta'):
                row.ruta_matriz = str(other)
            return r
        with patch.object(p, 'convertir', side_effect=conv):
            with self.assertRaises(p.ErrorPDFa):
                p.preparar(1, factory)
        self.assertEqual(row.ruta_matriz, str(other))
        self.assertTrue(sessions[1].rollback_called)
        self.assertEqual(other.read_bytes(), b'other operation')

    def test_commit_ack_lost_keeps_valid_persisted_references(self):
        row, factory, sessions, old = self.fake_session()
        persisted = {}
        def commit_ack_lost():
            persisted.update(matriz=row.ruta_matriz, consulta=row.ruta_consulta)
            raise RuntimeError('synthetic connection lost after commit')
        sessions[1].commit = commit_ack_lost
        with patch.object(p, 'convertir', side_effect=self.fake_convert):
            with self.assertRaises(RuntimeError):
                p.preparar(1, factory)
        self.assertTrue(all(Path(x).is_file() for x in persisted.values()))
        self.assertTrue(all(x.is_file() for x in old))


if __name__ == "__main__":
    unittest.main()
