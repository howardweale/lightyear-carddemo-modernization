"""CI-only disposable signing rehearsal; never uses configured production authority."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tests.test_decision_console_factory import FactoryTests
from lightyear_control_tower.factory_policy import FactoryDecisions, validate_contract
from lightyear_control_tower.decisions import digest
from tools.build_intcalc_signing_requests import build

ROOT = Path(__file__).resolve().parents[1]


def verify_order(requests, proofs, authority, root):
    if len(requests) != len(proofs): raise ValueError('signing-order-incomplete')
    previous = -1
    for contract, proof in zip(requests, proofs):
        validate_contract(contract, root)
        authority.verify(proof, contract['kind'], contract, ('accept', 'keep', 'approve'))
        event = next(e for e in proof['journal']['events'] if e['content_sha256'] == proof['decision_sha256'])
        if event['sequence'] <= previous: raise ValueError('signing-order')
        previous = event['sequence']


class OrderedSigningTests(FactoryTests):
    # Reuse only the disposable fixture, not its other test cases.
    def test_six_request_path(self):
        self.service.grant_roles('howard', ['operator','qualification-approver','business-owner','campaign-authorizer'],
            reason='Disposable CI rehearsal', workloads=['factory:INTCALC','factory:factory'])
        output=Path(self.temp.name)/'requests'
        index=build(ROOT,output)
        contracts=[json.loads((output/Path(r['path']).name).read_bytes()) for r in index['items']]
        for contract in contracts:
            for source in contract['sources']:
                dest=self.root/source['path'];dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/source['path'],dest)
        proofs=[]
        for contract in contracts[:5]:
            proof,_,_=self.decide(contract)
            proofs.append(proof)
        # Refresh earlier proofs to the same trusted current journal.
        proofs=[self.service.proof(self.token,p['decision_sha256']) for p in proofs]
        authority=FactoryDecisions(self.service.public_key,proofs[-1]['journal']['journal_head_sha256'],evidence_root=self.root)
        verify_order(contracts[:5],proofs,authority,self.root)
        with self.assertRaises(ValueError): verify_order(contracts[:5],list(reversed(proofs)),authority,self.root)
        with self.assertRaisesRegex(ValueError,'threshold-conditions-unmet'): self.decide(contracts[5])
        source=contracts[2]['sources'][0]
        (self.root/source['path']).write_bytes(b'changed after review')
        with self.assertRaises(ValueError): verify_order(contracts[:5],proofs,authority,self.root)


if __name__=='__main__':
    suite=unittest.TestSuite([OrderedSigningTests('test_six_request_path')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
