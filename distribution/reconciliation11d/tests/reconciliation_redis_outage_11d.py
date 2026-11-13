"""Run only while this isolated project's Redis has been deliberately stopped."""
import os
import unittest
import redis
import reconciliation_11d_tests as fixtures


class RedisOutage(unittest.TestCase):
    def test_real_redis_outage_preserves_reconciliation(self):
        self.assertTrue(os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-recon11d-'))
        r=redis.Redis.from_url(os.environ['CELERY_BROKER_URL'],socket_connect_timeout=2,socket_timeout=2)
        try:
            with self.assertRaises(redis.exceptions.ConnectionError):r.ping()
        finally:r.close()
        helper=fixtures.Reconciliation()
        d,_=helper.fixture()
        self.assertEqual(helper.run_reconcile(d)['state'],'RECONCILED')
        self.assertEqual(helper.run_reconcile(d)['state'],'RECONCILED')
        self.assertEqual(len(list(d.glob('reconciliation-*.json'))),1)


if __name__=='__main__':unittest.main(verbosity=2)
