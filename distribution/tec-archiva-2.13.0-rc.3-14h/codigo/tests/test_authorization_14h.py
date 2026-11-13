import base64
import copy
import unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from geology.nucleo import autorizacion_conciliacion as auth


class SignedAuthorization(unittest.TestCase):
    def setUp(self):
        self.authority=Ed25519PrivateKey.generate();self.runner=Ed25519PrivateKey.generate()
        public=lambda k:k.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.resources={'services':{'worker':{'id':'a'*64,'hostname':'clone'}},'volumes':{'clone-volume':{}},'networks':{'b'*64:{}}}
        self.policy={'version':1,'purpose':'rehearsal','authority_public_key':public(self.authority),'runner_public_key':public(self.runner),'max_seconds':300,'resources':self.resources,'target_services':['worker'],'storage_roots':['/cert'],'protected_resources':{'container_ids':['c'*64],'volume_names':['original-volume'],'network_ids':['d'*64]}}
        self.challenge={'protocol':1,'nonce':'f'*64,'pid':42,'start_ticks':'99','mount_namespace':5,'hostname':'clone','policy_sha256':auth.digest(self.policy)}
        self.ticket={'version':1,'id':'1'*32,'purpose':'rehearsal','action':'reconcile','max_runs':1,'policy_sha256':auth.digest(self.policy),'resource_sha256':auth.digest(self.resources),'target_service':'worker','target_container_id':'a'*64,'operation':'/cert/op','storage_root':'/cert','evidence_sha256':'2'*64,'issued_at':1000,'expires_at':1200}
    def envelope(self,key,value):return {'payload':value,'signature':base64.b64encode(key.sign(auth.canonical(value))).decode()}
    def packet(self,ticket=None,**changes):
        ticket=copy.deepcopy(ticket or self.ticket);ticket.update(changes);signed=self.envelope(self.authority,ticket)
        proof={'version':1,'issued_at':1000,'expires_at':1020,'ticket_sha256':auth.digest(signed),'challenge':self.challenge,'consumed':True,'resource_sha256':auth.digest(self.resources),'operation_evidence_sha256':ticket['evidence_sha256']}
        return {'authorization':signed,'execution':self.envelope(self.runner,proof)}
    def validate(self,packet=None,**kwargs):return auth.validate_packet(self.policy,self.challenge,packet or self.packet(),Path('/cert/op'),Path('/cert'),now=1001,**kwargs)
    def denied(self,packet):
        with self.assertRaises(Exception):self.validate(packet)
    def test_valid_specific_packet(self):self.assertEqual(self.validate()['id'],'1'*32)
    def test_missing_packet(self):self.denied({'authorization':self.packet()['authorization']})
    def test_unsigned_generic_document(self):self.denied({'authorization':{'payload':self.ticket,'signature':''},'execution':self.packet()['execution']})
    def test_bad_authority_signature(self):
        p=self.packet();p['authorization']['signature']=base64.b64encode(b'0'*64).decode();self.denied(p)
    def test_bad_attestor_signature(self):
        p=self.packet();p['execution']['signature']=base64.b64encode(b'0'*64).decode();self.denied(p)
    def test_expired(self):self.denied(self.packet(issued_at=800,expires_at=900))
    def test_future(self):self.denied(self.packet(issued_at=1100,expires_at=1200))
    def test_excess_lifetime(self):self.denied(self.packet(expires_at=1400))
    def test_wrong_policy(self):self.denied(self.packet(policy_sha256='0'*64))
    def test_wrong_resources(self):self.denied(self.packet(resource_sha256='0'*64))
    def test_wrong_container(self):self.denied(self.packet(target_container_id='b'*64))
    def test_wrong_operation(self):self.denied(self.packet(operation='/cert/other'))
    def test_wrong_action(self):self.denied(self.packet(action='delete'))
    def test_wrong_purpose(self):self.denied(self.packet(purpose='operation'))
    def test_multiple_runs(self):self.denied(self.packet(max_runs=2))
    def test_process_challenge_cannot_be_replayed(self):
        p=self.packet();self.challenge=copy.deepcopy(self.challenge);self.challenge['nonce']='0'*64;self.denied(p)
    def test_consumption_attestation_required(self):
        p=self.packet();p['execution']['payload']['consumed']=False;p['execution']=self.envelope(self.runner,p['execution']['payload']);self.denied(p)
    def test_rehearsal_rejects_protected_container_despite_name(self):
        self.resources['services']['worker']['id']='c'*64
        self.ticket.update(target_container_id='c'*64,policy_sha256=auth.digest(self.policy),resource_sha256=auth.digest(self.resources))
        self.denied(self.packet())
    def test_rehearsal_rejects_protected_volume(self):
        self.resources['volumes']={'original-volume':{}}
        self.ticket.update(policy_sha256=auth.digest(self.policy),resource_sha256=auth.digest(self.resources));self.denied(self.packet())
    def test_duplicate_json_keys(self):
        with self.assertRaises(auth.AuthorizationDenied):auth.decode('{"version":1,"version":2}')

