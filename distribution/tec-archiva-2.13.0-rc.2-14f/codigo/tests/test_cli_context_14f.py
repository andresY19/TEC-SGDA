import importlib.util
import io
import os
from pathlib import Path
import unittest
from types import ModuleType
from unittest.mock import patch

class LocalCLI(unittest.TestCase):
    def call(self,project='geology-restore14f',confirmation='geology-restore14f',environment='test',reading='no',result=None,error=None):
        import sys
        path=Path(__file__).resolve().parents[1]/'reconcile_documents.py'
        spec=importlib.util.spec_from_file_location('cli14f',path)
        module=importlib.util.module_from_spec(spec)
        domain=ModuleType('geology.dominio.conciliacion')
        domain.reconcile=lambda *args: None
        database=ModuleType('geology.nucleo.bd')
        database.SesionLocal=object()
        with patch.dict(sys.modules,{'geology.dominio.conciliacion':domain,'geology.nucleo.bd':database}):
            spec.loader.exec_module(module)
        argv=['reconcile_documents.py','--operation','/srv/geology/deposito/operation','--storage-root','/srv/geology/deposito']
        if confirmation is not None:argv+=['--local-project',confirmation]
        with patch.dict(os.environ,{'GEOLOGY_LOCAL_PROJECT':project,'GEOLOGY_ENTORNO':environment,'LEVANTAR_AL_CARGAR':reading}),patch.object(sys,'argv',argv),patch.object(module,'reconcile',return_value=result or {'state':'RECONCILED','outcome':'COMMITTED','reason':'CONFIRMED'},side_effect=error) as reconcile,patch('sys.stdout',new_callable=io.StringIO) as output:
            try:status=module.main()
            except SystemExit as exc:status=exc.code
            return status,output.getvalue(),reconcile.call_count
    def test_confirmed_local_project(self):self.assertEqual(self.call()[0],0)
    def test_legacy_namespace_preserved(self):self.assertEqual(self.call(project='geology-auto11e-test',confirmation=None)[0],0)
    def test_confirmation_required_outside_legacy(self):self.assertEqual(self.call(confirmation=None)[2],0)
    def test_wrong_confirmation(self):self.assertEqual(self.call(confirmation='other')[2],0)
    def test_original_is_blocked(self):self.assertEqual(self.call(project='geology-local-20261106-57a99a',confirmation='geology-local-20261106-57a99a')[2],0)
    def test_production_context_blocked(self):self.assertEqual(self.call(environment='production')[2],0)
    def test_project_format_rejected(self):self.assertEqual(self.call(project='../escape',confirmation='../escape')[2],0)
    def test_ia_enabled_rejected(self):self.assertEqual(self.call(reading='yes')[2],0)
    def test_ambiguous_exit_code(self):self.assertEqual(self.call(result={'state':'NEEDS_REVIEW','outcome':'UNCERTAIN','reason':'MISSING_EVIDENCE'})[0],2)
    def test_unavailable_does_not_leak_exception(self):
        code,output,calls=self.call(error=RuntimeError('SECRET_SYNTHETIC'))
        self.assertEqual(code,2);self.assertNotIn('SECRET_SYNTHETIC',output);self.assertIn('NEEDS_REVIEW',output)
