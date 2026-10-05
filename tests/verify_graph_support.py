"""Public/synthetic fixtures only. No Docker, subprocess candidate or model calls."""
import asyncio
import copy
import gzip
import json
import tempfile
import unittest
import uuid
import importlib.util
import io
import os
import shutil
from contextlib import redirect_stderr
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from lightyear_control_tower.decisions import canonical, digest
from lightyear_mainframe.zos_evidence import initialize_key, Signer
from lightyear_judge.graph_projection import build, read, leak_check, tainted
from lightyear_judge.graph_cli import request
from lightyear_toolkit.graph_approval import load_approved, receipt_context, sha

ROOT=Path(__file__).resolve().parents[1]


class GraphFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        initialize_key(self.root/"operator.pem")
        self.signer=Signer(self.root/"operator.pem")
        self.policy=ROOT/"verify/graph-projection-policy.json"
        self.lane=read(self.policy)["lanes"]["INTCALC"]
        self.out=self.root/"projection"


    def build(self, **kw):
        return build(ROOT/"knowledge/graph.snapshot.json.gz",ROOT/"knowledge/evidence/source.pack.json.gz",
            self.policy,"INTCALC",kw.pop("mode","field"),"carddemo-reference",
            kw.pop("out",self.out),self.signer,source_root=ROOT,**kw)


    def approve(self, manifest, *, outcome="approved", reason="Reviewed public source projection"):
        from lightyear_control_tower.console import ConsoleService, provision
        tower=self.root/("tower-"+uuid.uuid4().hex)
        tower.mkdir()
        authority=self.root/(tower.name+"-authority")/"authority.json"
        credential=provision(authority,"verify-graph","howard","Howard").read_text().strip()
        console=ConsoleService(tower,authority)
        self.addCleanup(console.close)
        console.grant_roles("howard",["operator","qualification-approver"],reason="Fixture")
        token=console.login(credential)["token"]
        report=read(self.out/"leak-check.json")
        request(tower,"verify-graph",self.out,self.policy,self.lane,manifest,report)
        item=console.review(token,"graph-"+manifest["projection_sha256"][:24])
        e=console.decide(token,dict(item_id=item["id"],bound=item["bound"],outcome=outcome,
            reason=reason,named_owner="Howard",review_after=(datetime.now(timezone.utc)+timedelta(days=10)).date().isoformat(),
            previous_decision_sha256=None,request_id=str(uuid.uuid4())))
        proof=console.proof(token,e["content_sha256"])
        # The console exposes the authority key through its signed export.
        key=console.public_key
        trust=dict(operator_key=self.signer.public.decode(),judge_key=self.signer.public.decode(),
            tower_key=key.decode(),trusted_head=proof["journal"]["journal_head_sha256"],
            lane_sha256=digest(self.lane),scope="verify-graph",mode=manifest["mode"],
            customer_id="carddemo-reference")
        return proof,trust
