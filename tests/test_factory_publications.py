"""CI-only Git data fixtures; signature verification is explicitly mocked, never signed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import check_factory_publications as checker

TRUST = "factory@lightyear.invalid ssh-ed25519 Zml4dHVyZQ==\n"


class FactoryMainPublicationTests(unittest.TestCase):
    def git(self, root, *args, data=None):
        return subprocess.check_output(["git", "-C", str(root), *args], input=data,
                                       stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, root, message="fixture"):
        self.git(root, "add", "-A")
        self.git(root, "-c", "commit.gpgsign=false", "commit", "--no-verify", "--allow-empty", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def fixture(self, directory, *, reverted_human=False):
        root=Path(directory)/"repository";root.mkdir()
        self.git(root,"init");self.git(root,"config","user.name","Fixture")
        self.git(root,"config","user.email","fixture@example.invalid")
        base=self.commit(root,"Factory run start")
        candidate=root/"unit.txt";candidate.write_bytes(b"candidate bytes\n")
        def message(attempt):
            return f"Factory candidate attempt {attempt}\n\nFactory-Run: run-fixture\nFactory-Attempt: {attempt}\nFactory-Provenance: " + "a"*64
        end=self.commit(root,message(1));human=None
        if reverted_human:
            candidate.write_bytes(b"human change\n");human=self.commit(root,message(2))
            candidate.write_bytes(b"candidate bytes\n");end=self.commit(root,message(3))
        tree=self.git(root,"rev-parse",end+"^{tree}")
        stem=root/checker.REGISTRY/"run-fixture";(stem/"package").mkdir(parents=True)
        (stem/"package/unit.txt").write_bytes(candidate.read_bytes());candidate.unlink()
        value=dict(schema="factory-main-publication/1",run_id="run-fixture",candidate_base=base,
            candidate_commit=end,candidate_tree=tree,source_receipt_sha256="b"*64)
        (stem/"publication.json").write_text(json.dumps(value))
        main=self.commit(root)
        return root,base,end,main,stem,human

    def verify(self, root, main, directory):
        return checker.verify_main(root,main,TRUST,Path(directory))

    def test_exact_package_uses_signed_history_and_never_executes_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root,base,end,main,stem,human=self.fixture(directory)
            with patch.object(checker,"verify_signature") as signature:
                result=self.verify(root,main,directory)
            self.assertEqual("verified",result["status"])
            self.assertFalse(result["factory_run_acceptance"])
            self.assertEqual(end,result["packages"][0]["candidate_commit"])
            self.assertEqual(1,result["packages"][0]["files"])
            self.assertEqual(end,signature.call_args.args[1]);signature.assert_called_once()
            empty=checker.verify_main(root,base,"",Path(directory))
            self.assertEqual("no-candidates",empty["status"])

    def test_byte_path_mode_and_link_interventions_fail(self):
        for change in ("bytes","extra","deleted","mode","link"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                root,base,end,main,stem,human=self.fixture(directory)
                target=stem/"package/unit.txt"
                if change=="bytes":target.write_bytes(b"human mutation")
                if change=="extra":(stem/"package/extra.txt").write_bytes(b"extra")
                if change=="deleted":target.unlink()
                self.git(root,"add","-A")
                relative=target.relative_to(root).as_posix()
                if change=="mode":self.git(root,"update-index","--chmod=+x",relative)
                if change=="link":
                    oid=self.git(root,"hash-object","-w","--stdin",data=b"outside")
                    self.git(root,"update-index","--cacheinfo","120000,"+oid+","+relative)
                self.git(root,"-c","commit.gpgsign=false","commit","--no-verify","-m","intervention")
                main=self.git(root,"rev-parse","HEAD")
                with patch.object(checker,"verify_signature"),self.assertRaises(checker.Intervention):
                    self.verify(root,main,directory)

    def test_removed_or_rewritten_manifest_and_unbound_package_fail(self):
        for change in ("remove","rewrite","unbound"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                root,base,end,main,stem,human=self.fixture(directory)
                path=stem/"publication.json"
                if change=="remove":path.unlink()
                if change=="rewrite":
                    value=json.loads(path.read_text());value["source_receipt_sha256"]="c"*64
                    path.write_text(json.dumps(value))
                if change=="unbound":(root/checker.REGISTRY/"unbound.txt").write_bytes(b"unbound")
                main=self.commit(root)
                with patch.object(checker,"verify_signature"),self.assertRaises(checker.Intervention):
                    self.verify(root,main,directory)

    def test_reverted_human_commit_is_not_hidden_by_matching_final_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root,base,end,main,stem,human=self.fixture(directory,reverted_human=True)
            checked=[]
            def signature(root,commit,trust):
                checked.append(commit)
                if commit==human:raise checker.Intervention("unsigned fixture commit")
            with patch.object(checker,"verify_signature",side_effect=signature),self.assertRaises(checker.Intervention):
                self.verify(root,main,directory)
            self.assertIn(human,checked)

    def test_external_trust_and_signature_refusal_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root,base,end,main,stem,human=self.fixture(directory)
            for trust in ("",TRUST+TRUST,TRUST.replace("factory@lightyear.invalid","attacker@example.invalid")):
                with self.subTest(trust=trust),self.assertRaises(checker.Intervention):
                    checker.verify_main(root,main,trust,Path(directory))
            with patch.object(checker,"verify_signature",side_effect=checker.Intervention("unsigned")),self.assertRaises(checker.Intervention):
                self.verify(root,main,directory)
            with self.assertRaises(checker.Intervention):checker.verify_main(root,main,TRUST,root)

    def test_cli_refuses_non_main_context_before_candidate_access(self):
        for event,ref in (("pull_request","refs/pull/1/merge"),("push","refs/heads/topic"),("workflow_dispatch","refs/heads/main")):
            with self.subTest(event=event,ref=ref),patch.dict(os.environ,dict(GITHUB_ACTIONS="true",
                    GITHUB_EVENT_NAME=event,GITHUB_REF=ref,GITHUB_SHA="a"*40)), \
                 patch("sys.argv",["check_factory_publications.py"]),patch.object(checker,"verify_main") as verify, \
                 patch("builtins.print"),self.assertRaises(SystemExit) as exc:
                checker.main()
            self.assertEqual(1,exc.exception.code);verify.assert_not_called()

    def test_signature_adapter_uses_verification_only_and_external_trust(self):
        with patch.object(checker,"git") as git:
            checker.verify_signature(Path("repo"),"a"*40,Path("external-trust"))
        args=git.call_args.args
        self.assertEqual(("verify-commit","a"*40),args[-2:])
        self.assertIn("gpg.ssh.allowedSignersFile=external-trust",args)
        self.assertNotIn("commit-tree",args);self.assertNotIn("-S",args)


if __name__ == "__main__":
    unittest.main()
