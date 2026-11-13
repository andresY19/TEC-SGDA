"""Casos del nuevo contrato; Redis real se certifica mediante HTTP en aislamiento."""
import os
import unittest
from unittest.mock import patch
from geology.nucleo import pases, sesiones


class RegistroSesiones(unittest.TestCase):
    def test_01_invalid_crypto_never_contacts_storage(self):
        with patch.object(sesiones,'_cliente',side_effect=AssertionError('unexpected Redis')) as client:
            self.assertFalse(sesiones.validar('invalid', 'synthetic'))
            client.assert_not_called()

    def test_02_configuration_failure_is_sanitized(self):
        for url in ['', 'redis://:synthetic-private@host/0','https://host/2']:
            with patch.dict(os.environ,{'AUTH_REDIS_URL':url,'GEOLOGY_LOCAL_PROJECT':'session-unit'}):
                with self.assertRaises(sesiones.SesionesNoDisponibles) as ctx:
                    sesiones._cliente()
                self.assertNotIn('synthetic-private',str(ctx.exception))

    def test_03_storage_keys_do_not_expose_identity_or_token_id(self):
        with patch.dict(os.environ,{'GEOLOGY_CLAVE':'unit-only-key-'*4}):
            claims={'sub':'synthetic@example.invalid','jti':'A'*22}
            keys=sesiones._keys('project:auth:v1:',claims)
            self.assertTrue(all(claims['sub'] not in x and claims['jti'] not in x for x in keys))
            self.assertNotEqual(*keys)

    def test_04_claims_keep_existing_crypto_contract(self):
        with patch.dict(os.environ,{'GEOLOGY_CLAVE':'unit-only-key-'*4}):
            token=pases.crear_pase('synthetic@example.invalid')
            self.assertEqual(pases.detalles_pase(token)['sub'],pases.leer_pase(token))
            self.assertTrue(token.startswith('g1.'))
