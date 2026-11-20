"""Synthetic validation only. Never calls worker(), operation(), main() or generator."""
import copy
import unittest
from tools import intcalc_private_answer_session as s
from tools import intcalc_private_answer_worker as w


class SessionTests(unittest.TestCase):
    def policy(self):
        return dict(schema='heldout-answer-policy/1',count=16,source_hashes={str(i):'a'*64 for i in range(7)},
            worker_sha256='b'*64,generator_sources={},reference_binding={'path':'binding.json','sha256':'c'*64},
            package_library_sha256=s.hostlib.PACKAGE,age={'path':'/age','sha256':'d'*64,'version':'reviewed'},
            recipient='age1'+'q'*58,recipient_sha256=s.stream.sha(('age1'+'q'*58).encode()),recipient_designation_sha256='f'*64,
            host_canary_sha256='1'*64,licence_review_sha256='2'*64)
    def state(self):
        return dict(Config=dict(Image='image',User='1000:1000',OpenStdin=True,Tty=False),
            HostConfig=dict(NetworkMode='none',ReadonlyRootfs=True,CapDrop=['ALL'],Memory=2147483648,
                PidsLimit=128,NanoCpus=2000000000,LogConfig={'Type':'none'},CgroupnsMode='private',
                Privileged=False,Devices=[],Binds=[],SecurityOpt=['no-new-privileges'],Tmpfs={'/work':'','/tmp':''}),
            Mounts=[dict(Destination='/source',Source='/source-root',Type='bind',RW=False),
                    dict(Destination='/answer-policy.json',Source='/policy',Type='bind',RW=False)])
    def check(self,row):s.boundary(row,'image','/source-root','/policy','1000:1000')
    def test_policy_bound(self):s.policy(self.policy())
    def test_policy_unknown_key(self):
        p=self.policy();p['seed']='forbidden'
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_policy_unbound_age(self):
        p=self.policy();p['age']['sha256']=None
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_policy_unbound_canary(self):
        p=self.policy();p['host_canary_sha256']=None
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_policy_count_boolean(self):
        p=self.policy();p['count']=True
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_policy_count_too_many(self):
        p=self.policy();p['count']=65
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_policy_path_escape(self):
        p=self.policy();p['source_hashes']['../escape']='a'*64
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_policy_inventory_mismatch(self):
        p=self.policy();p['package_library_sha256']='0'*64
        with self.assertRaises(s.stream.Refused):s.policy(p)
    def test_boundary_closed(self):self.check(self.state())
    def test_network_refused(self):
        r=self.state();r['HostConfig']['NetworkMode']='bridge'
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_persistent_output_mount_refused(self):
        r=self.state();r['Mounts'].append(dict(Destination='/output',Source='/private',Type='bind',RW=True))
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_writable_source_refused(self):
        r=self.state();r['Mounts'][0]['RW']=True
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_logging_refused(self):
        r=self.state();r['HostConfig']['LogConfig']['Type']='json-file'
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_tty_refused(self):
        r=self.state();r['Config']['Tty']=True
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_no_stdin_refused(self):
        r=self.state();r['Config']['OpenStdin']=False
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_no_private_cgroup_refused(self):
        r=self.state();r['HostConfig']['CgroupnsMode']='host'
        with self.assertRaises(s.stream.Refused):self.check(r)
    def test_wrong_limits_refused(self):
        for key,value in [('Memory',0),('PidsLimit',-1),('NanoCpus',0),('Privileged',True)]:
            r=self.state();r['HostConfig'][key]=value
            with self.subTest(key=key),self.assertRaises(s.stream.Refused):self.check(r)
    def test_tmpfs_real_mount_required(self):
        w.mount_tmpfs('1 2 0:1 / /work rw - tmpfs tmpfs rw','/work')
        with self.assertRaises(s.stream.Refused):w.mount_tmpfs('1 2 0:1 / /work rw - ext4 disk rw','/work')
    def test_tmpfs_duplicate_refused(self):
        with self.assertRaises(s.stream.Refused):w.mount_tmpfs(('1 2 0:1 / /work rw - tmpfs tmpfs rw\n')*2,'/work')
    def test_fixed_refusal(self):
        self.assertEqual(s.refusal(ValueError('private-canary')),'answer-fault')
        self.assertEqual(s.refusal(s.stream.Refused('answer-clock')),'answer-clock')
    def test_canary_exact_hash_and_claims(self):
        p=self.policy();row=dict(schema='heldout-age-host-canary/1',operator='Howard',encryptor_sha256='d'*64,
            recipient_sha256=p['recipient_sha256'],public_canary_only=True,roundtrip_match=True,interruption_refused=True,
            exclusive_write=True,file_directory_sync_readback=True,usb_identity_only=True,raw_private_values_included=False)
        raw=s.stream.canonical(row);p['host_canary_sha256']=s.stream.sha(raw);s.canary_receipt(raw,p)
        for key in ('roundtrip_match','interruption_refused','usb_identity_only'):
            bad=copy.deepcopy(row);bad[key]=False;b=s.stream.canonical(bad);p['host_canary_sha256']=s.stream.sha(b)
            with self.subTest(key=key),self.assertRaises(s.stream.Refused):s.canary_receipt(b,p)
    def test_canary_changed_bytes_refused(self):
        with self.assertRaises(s.stream.Refused):s.canary_receipt(b'{}',self.policy())


if __name__=='__main__':unittest.main()
