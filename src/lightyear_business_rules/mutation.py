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


def mutants(source):
    monthly = 'balance.balance()\n                    .multiply(disclosure.annualRate())\n                    .divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)'
    changes = {
        "boundary-shift": ('disclosure.annualRate().signum() == 0', 'disclosure.annualRate().signum() <= 0'),
        "rounding-mode": ('.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)', '.divide(BigDecimal.valueOf(1200), 2, RoundingMode.HALF_UP)'),
        "operand-swap": (monthly, 'BigDecimal.valueOf(1200).divide(balance.balance().multiply(disclosure.annualRate()), 2, RoundingMode.DOWN)'),
        "dropped-branch": ('"intended".equals(finalAccountPolicy) && currentAccount != null', 'currentAccount != null'),
        "scale-plus-one": ('.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)', '.divide(BigDecimal.valueOf(1200), 3, RoundingMode.DOWN)'),
        "scale-minus-one": ('.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)', '.divide(BigDecimal.valueOf(1200), 1, RoundingMode.DOWN)'),
        "one-cent-smoke": ('.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)', '.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN).add(new BigDecimal("0.01"))'),
    }
    for name, (old, new) in changes.items():
        require(source.count(old) == 1, "mutation-anchor-changed")
        yield name, source.replace(old, new)


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
    require(manifest["evidence_class"] == "synthetic-public-rehearsal", "public-mutation-only")
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
    variants = [("baseline", source, "service"), *[(n,s,"service") for n,s in mutants(source)],
                ("codec-scale-minus-one", codec.replace(codec_anchor, "ZonedDecimal.encode(value.amount(), 11, 1)"), "codec")]
    results = []
    for name, text, target in variants:
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
        results.append(dict(name=name, target=target, source_sha256=sha256(text.encode()).hexdigest(), **verdict))
    rows = []
    statuses = {r["id"]:r["status"] for r in receipt["rules"]}
    for rule in rules:
        if statuses[rule["id"]] != "verified": continue
        applicable = [r for r in results[1:] if any(
            t.endswith("InterestCalculationService#calculate") if r["target"] == "service" else "CardDemoRecordCodec#" in t
            for t in rule.get("implemented_by", []))]
        outcomes = [{**r, "killed": killed(r, rule["outputs"])} for r in applicable]
        count = sum(r["killed"] for r in outcomes)
        rows.append(dict(id=rule["id"], generated=len(outcomes), killed=count, kill_rate=count/len(outcomes) if outcomes else None,
                         mutants=outcomes, limitation=None if outcomes else "No supported mutation anchor for this implementation target."))
    return dict(schema="lightyear-rule-mutations/1", rule_set_sha256=digest(rules), receipt_sha256=receipt["content_sha256"],
                rules=rows, model_calls=0, docker_calls=0, baseline=results[0],
                limitation="Modern service mutations against public synthetic captured records; surviving and inapplicable operators are retained.")
