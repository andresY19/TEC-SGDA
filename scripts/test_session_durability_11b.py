"""Failure branches of durable acknowledgement; no real connection or secrets."""
import unittest
from unittest.mock import MagicMock
from geology.nucleo import sesiones


class DurableAcknowledgement(unittest.TestCase):
    def client(self):
        client=MagicMock();pipeline=client.pipeline.return_value.__enter__.return_value
        return client,pipeline

    def test_01_missing_local_aof_ack_cannot_report_success(self):
        client,pipeline=self.client();pipeline.execute.return_value=['OK',[0,0]]
        with self.assertRaises(sesiones.SesionesNoDisponibles):
            sesiones._durable(client,'return 1',['synthetic'],[])
        client.pipeline.assert_called_once_with(transaction=False)
        pipeline.execute_command.assert_called_once_with('WAITAOF',1,0,2000)
        client.close.assert_called_once()

    def test_02_backend_exception_is_sanitized(self):
        client,pipeline=self.client();pipeline.execute.side_effect=RuntimeError('synthetic-private-value')
        with self.assertRaises(sesiones.SesionesNoDisponibles) as error:
            sesiones._durable(client,'return 1',['synthetic'],[])
        self.assertNotIn('synthetic-private-value',str(error.exception));client.close.assert_called_once()


if __name__=='__main__':unittest.main(verbosity=2)
