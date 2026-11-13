"""The old environment confirmation no longer grants implicit authority."""
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class LocalCLI(unittest.TestCase):
    def invoke(self, project, confirmation=None, environment='test', operation='/cert/operation'):
        path=Path(__file__).resolve().parents[1]/'reconcile_documents.py'
        spec=importlib.util.spec_from_file_location('cli14h',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        args=['reconcile_documents.py','--operation',operation,'--storage-root','/cert']
        if confirmation is not None:args+=['--local-project',confirmation]
        with patch.dict(os.environ,{'GEOLOGY_LOCAL_PROJECT':project,'GEOLOGY_ENTORNO':environment}),patch.object(sys,'argv',args),patch('sys.stdout',new_callable=io.StringIO):
            return module.main()
    def test_confirmation_alone_denied(self):self.assertEqual(self.invoke('geology-clone','geology-clone'),77)
    def test_legacy_namespace_alone_denied(self):self.assertEqual(self.invoke('geology-auto11e-test'),77)
    def test_no_confirmation_denied(self):self.assertEqual(self.invoke('geology-clone'),77)
    def test_wrong_confirmation_denied(self):self.assertEqual(self.invoke('geology-clone','other'),77)
    def test_protected_display_name_denied(self):self.assertEqual(self.invoke('geology-local-20261106-57a99a','geology-local-20261106-57a99a'),77)
    def test_production_context_denied(self):self.assertEqual(self.invoke('geology-clone','geology-clone','production'),77)
    def test_renamed_project_denied(self):self.assertEqual(self.invoke('renamed-local','renamed-local'),77)
    def test_force_variable_does_not_authorize(self):
        with patch.dict(os.environ,{'FORCE':'true'}):self.assertEqual(self.invoke('geology-clone','geology-clone'),77)
    def test_different_operation_still_requires_authority(self):self.assertEqual(self.invoke('geology-clone',operation='/cert/other'),77)
    def test_no_external_context_required_for_default_denial(self):
        with patch.dict(os.environ,{},clear=True):self.assertEqual(self.invoke(''),77)
