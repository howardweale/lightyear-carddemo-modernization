"""CI import qualification for the standalone, unsigned APPL-RESULT packets."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.factory_import import import_request
from lightyear_control_tower.factory_policy import FactoryInbox
from lightyear_control_tower.kinds import factory_registry

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'docs/factory/appl-result-signing-2026-10-16'


def sha(raw): return hashlib.sha256(raw).hexdigest()


def verified(value):
    body = {k:v for k,v in value.items() if k != 'content_sha256'}
    # Historical #341 seals use json's ASCII escaping.
    raw = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
    if sha(raw) != value['content_sha256']: raise ValueError('seal-mismatch')
    return value


class ApplClassPackets(unittest.TestCase):
    def test_canonical_contract_hashes_full_members_and_audits(self):
        manifest = verified(json.loads((PACKET/'manifest.json').read_bytes()))
        for row in manifest['requests']:
            raw = (ROOT/row['contract_path']).read_bytes()
            contract = json.loads(raw)
            self.assertEqual(raw, canonical(contract))
            self.assertEqual(row['contract_sha256'], sha(raw))
            self.assertEqual('factory-'+sha(raw), row['request_id'])
            self.assertEqual('twin', contract['details']['claim_scope'])
            folder = PACKET/row['program']
            request = json.loads((folder/'class-request.json').read_bytes())
            proof = verified(request['class_proof'])
            audit = verified(json.loads((folder/'audit.json').read_bytes()))
            census = verified(json.loads((folder/'census.json').read_bytes()))
            packet = verified(json.loads((folder/'class-packet.json').read_bytes()))
            self.assertEqual(contract, request['contract'])
            self.assertEqual(proof['content_sha256'], contract['details']['class_proof_sha256'])
            self.assertEqual(packet['matches'], proof['matches'])
            self.assertEqual(sorted(proof['matches']), contract['details']['items'])
            self.assertEqual(row['members'], len(set(contract['details']['items'])))
            self.assertEqual(contract['details']['items'], audit['members'])
            self.assertEqual(30, len({r['id'] for r in audit['sample']}))
            self.assertTrue(census['passed']); self.assertEqual([], census['raw_consumers'])
            self.assertEqual(census['source_sha256'], sha((folder/'source.cbl.txt').read_bytes()))
            self.assertEqual(proof['matcher_sha256'], sha((folder/'matcher.py.txt').read_bytes()))
            for binding in contract['sources']:
                self.assertEqual(manifest['evidence_commit'], binding['commit'])
                self.assertEqual(binding['sha256'], sha((ROOT/binding['path']).read_bytes()))

    def test_importer_real_git_blobs_and_hash_refusal_without_signing(self):
        # A local temporary CI Git repo avoids relying on shallow-checkout
        # ancestors. The above test checks every actual publication binding.
        # Historical byte qualification is above. These new synthetic item sets
        # exercise git-show/hash refusal without impersonating the selected classes.
        from tests import test_decision_console_factory as fixtures
        fixture=fixtures.FactoryTests('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups)
        journal=fixture.service.export_session(fixture.token)
        trust=dict(journal=journal,public_key=fixture.service.public_key,trusted_head=journal['journal_head_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); repo = base/'repo'; repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-c','core.autocrlf=false',
                    '-c','commit.gpgsign=false','-c','user.name=Packet CI',
                    '-c','user.email=packet-ci@example.invalid',*args],cwd=repo)
            git('init')
            contracts = []
            for program in ('INTCALC','POSTTRAN'):
                contract = json.loads((PACKET/program/'contract.json').read_bytes())
                for binding in contract['sources']:
                    dest = repo/binding['path']; dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes((ROOT/binding['path']).read_bytes())
                contracts.append(contract)
            git('add','.'); git('commit','-m','Synthetic CI import fixture; public bytes only')
            commit = git('rev-parse','HEAD').decode().strip()
            for program, original in zip(('INTCALC','POSTTRAN'),contracts):
                contract = copy.deepcopy(original)
                for source in contract['sources']: source['commit'] = commit
                contract['details']['items']=['synthetic-ci-'+program+'-1','synthetic-ci-'+program+'-2']
                contract['details']['class_proof_sha256']=None
                tower = base/program
                item = import_request(repo,tower,contract,**trust)
                self.assertEqual('factory-'+sha(canonical(contract)),item['id'])
                FactoryInbox(tower,'factory',factory_registry()).item(item['id'])
                # A second identical import is idempotent; no signature is made.
                self.assertEqual(item,import_request(repo,tower,contract,**trust))
                bad = copy.deepcopy(contract);bad['sources'][0]['sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'public-commit-byte-mismatch'):
                    import_request(repo,base/('bad-'+program),bad,**trust)
                self.assertFalse((base/('bad-'+program)).exists())


if __name__ == '__main__': unittest.main()
