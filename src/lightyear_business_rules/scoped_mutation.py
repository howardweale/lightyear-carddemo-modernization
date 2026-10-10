"""Host-only modern Java mutations and the judge's existing record comparator."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from lightyear_control_tower.decisions import digest
from lightyear_mainframe.records import load_copybook, decode_fixed, from_ascii_fixed
from lightyear_mainframe.zos_compare import compare_records
from .language import require


def killed(verdict, output_fields):
    return verdict.get("status") == "divergent" and bool(set(verdict.get("fields", [])) & set(output_fields))


RUNNER = '''import java.nio.file.*;
import java.util.*;
import ai.lightyear.carddemo.codec.CardDemoRecordCodec;
import ai.lightyear.carddemo.service.InterestCalculationService;
public class RuleRunner {
 public static void main(String[] a) throws Exception {
  Path p=Path.of(a[0]);
  var r=new InterestCalculationService().calculate(
   Files.readAllLines(p.resolve("TCATBALF")).stream().map(CardDemoRecordCodec::parseCategoryBalance).toList(),
   Files.readAllLines(p.resolve("DISCGRP")).stream().map(CardDemoRecordCodec::parseDisclosure).toList(),
   Files.readAllLines(p.resolve("XREFFILE")).stream().map(CardDemoRecordCodec::parseCardXref).toList(),
   Files.readAllLines(p.resolve("ACCTFILE")).stream().map(CardDemoRecordCodec::parseAccount).toList(), a[2],a[3],"source-faithful");
  Path out=Path.of(a[1]);
  Files.write(out.resolve("ACCTFILE"),r.accounts().stream().map(CardDemoRecordCodec::renderAccount).toList());
  Files.write(out.resolve("TRANSACT"),r.transactions().stream().map(CardDemoRecordCodec::renderTransaction).toList());
 }
}'''


def run(root, fixture, work, jdk, rules, receipt):
    root, fixture, work, jdk = map(Path, (root, fixture, work, jdk))
    require(not work.exists(), "mutation-output-exists")
    require("arrivals" not in fixture.resolve().parts, "private-mutation-refused")
    manifest = json.loads((fixture / "run.json").read_text(encoding="utf-8"))
    require(manifest["evidence_class"] in {"synthetic-public-rehearsal", "synthetic-public-reference-model"}, "public-mutation-only")
    work.mkdir(parents=True)
    inputs = work / "inputs"
    inputs.mkdir()
    for d in manifest["datasets"]:
        if d["phase"] == "before":
            raw = (fixture / d["file"]).read_bytes()
            require(len(raw) % d["lrecl"] == 0, "mutation-record-length")
            (inputs / d["dd"]).write_text("\n".join(raw[i:i+d["lrecl"]].decode(d["codec"]) for i in range(0,len(raw),d["lrecl"]))+"\n", encoding="ascii")
    base = root / "candidate-java/src/main/java/ai/lightyear/carddemo"
    source = (base / "service/InterestCalculationService.java").read_text(encoding="utf-8")
    codec = (base / "codec/CardDemoRecordCodec.java").read_text(encoding="utf-8")
    codec_anchor = "ZonedDecimal.encode(value.amount(), 11, 2)"
    require(codec.count(codec_anchor) == 1, "codec-mutation-anchor-changed")
    from .operators import anchored_variants, CardDemoAdapter
    variants = [dict(name="baseline", text=source, target="service", rule_id=None, anchor=None)]
    for rule in rules:
        for variant in anchored_variants(source, rule, CardDemoAdapter()):
            variant["name"] = rule["id"].split(":")[-1]+"--"+variant["name"]
            variants.append(variant)
    results = []
    for variant in variants:
        name, text, target = (variant[k] for k in ("name", "text", "target"))
        directory = work / name
        directory.mkdir()
        paths = []
        for filename, body in [("InterestCalculationService.java",text if target == "service" else source),
             ("CardDemoRecordCodec.java",text if target == "codec" else codec), ("RuleRunner.java",RUNNER),
             ("Service.java", "package org.springframework.stereotype; public @interface Service {}")]:
            p = directory / filename
            p.write_text(body, encoding="utf-8")
            paths.append(str(p))
        paths += [str(base / p) for p in ("domain/Records.java", "codec/ZonedDecimal.java")]
        suffix = ".exe" if os.name == "nt" else ""
        compile_result = subprocess.run([str(jdk/("bin/javac"+suffix)), "-d", str(directory), *paths], capture_output=True, timeout=90)
        require(compile_result.returncode == 0, "mutation-compile-failed")
        execution = subprocess.run([str(jdk/("bin/java"+suffix)), "-cp", str(directory), "RuleRunner", str(inputs), str(directory),
            manifest["processing_date"], manifest["candidate_timestamp"]], capture_output=True, timeout=60)
        fields, identical = [], True
        if execution.returncode == 0:
            for dd, cpy in (("ACCTFILE","CVACT01Y"), ("TRANSACT","CVTRA05Y")):
                layout = load_copybook(root / f"spec/mainframe/copybooks/{cpy}.cpy")
                expected = decode_fixed(layout, (fixture/f"after/{dd}.bin").read_bytes(), codec="cp037")
                actual = from_ascii_fixed(layout, (directory/dd).read_bytes(), codec="cp037")
                comparison = compare_records(expected, actual, {"keys": [], "timestamp_fields": []}, base_rules=True)
                identical &= comparison["identical"]
                for change in comparison["fields"]:
                    field = next(f for f in layout.fields if f.path == change["path"])
                    fields.extend((f"legacy:cobol-field:{cpy}:{field.path.split('.')[-1]}:{field.line}", f"legacy:copybook:{cpy}"))
            verdict = dict(status="equivalent" if identical else "divergent", fields=sorted(set(fields)))
        else:
            verdict = dict(status="execution-failure", fields=[])
        if name == "baseline":
            require(verdict["status"] == "equivalent", "baseline-not-equivalent")
        results.append(dict(name=name, target=target, rule_id=variant["rule_id"], anchor=variant["anchor"], source_sha256=sha256(text.encode()).hexdigest(), **verdict))
    failure_case = None
    if manifest.get("expected_failure"):
        failure_inputs = work / "missing-disclosure-inputs"
        failure_inputs.mkdir()
        for item in manifest["expected_failure"]["datasets"]:
            raw = (fixture/item["file"]).read_bytes()
            require(sha256(raw).hexdigest() == item["sha256"], "failure-fixture-hash")
            dd = Path(item["file"]).stem
            (failure_inputs/dd).write_text("\n".join(raw[i:i+item["lrecl"]].decode("cp037") for i in range(0,len(raw),item["lrecl"]))+("\n" if raw else ""),encoding="ascii")
        execution = subprocess.run([str(jdk/("bin/java"+suffix)), "-cp", str(work/"baseline"), "RuleRunner", str(failure_inputs), str(failure_inputs),
            manifest["processing_date"], manifest["candidate_timestamp"]],capture_output=True,timeout=60)
        failure_case = dict(expected="execution-failure", actual="execution-failure" if execution.returncode else "success",
            message_matched=manifest["expected_failure"]["message"].encode() in execution.stderr,
            stderr_sha256=sha256(execution.stderr).hexdigest())
        require(failure_case["actual"] == failure_case["expected"] and failure_case["message_matched"], "missing-disclosure-candidate-disagreement")
    rows = []
    for rule in rules:
        applicable = [r for r in results[1:] if r["rule_id"] == rule["id"]]
        outcomes = []
        for result in applicable:
            output_nodes = {v["node"] for k,v in rule.get("bindings", {}).items() if k.startswith("output.") and v["node"].startswith("legacy:cobol-field:")}
            # Record-presence predicates have copybook-level output bindings.
            if not output_nodes:
                output_nodes = set(rule["outputs"])
            outcome = "killed-failure" if result["status"] == "execution-failure" else "killed-divergent" if killed(result, output_nodes) else "survived"
            outcomes.append({**result, "outcome": outcome, "killed": outcome.startswith("killed-")})
        divergent = sum(m["outcome"] == "killed-divergent" for m in outcomes)
        failure = sum(m["outcome"] == "killed-failure" for m in outcomes)
        rows.append(dict(id=rule["id"], generated=len(outcomes), killed=divergent+failure,
            killed_divergent=divergent, killed_failure=failure,
            kill_rate=(divergent+failure)/len(outcomes) if outcomes else None, mutants=outcomes,
            outcome=None if outcomes else "not-applicable",
            limitation=None if outcomes else "No reviewed modern edit anchor for this rule; no service-wide mutants borrowed."))
    return dict(schema="lightyear-rule-mutations/2", rule_set_sha256=digest(rules), receipt_sha256=receipt["content_sha256"],
                rules=rows, model_calls=0, docker_calls=0, baseline=results[0], missing_disclosure=failure_case,
                limitation="Rule-scoped modern Java mutations versus public reference-model outputs, not legacy execution.")
