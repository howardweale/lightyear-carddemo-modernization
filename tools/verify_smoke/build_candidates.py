"""Build exactly the public acceptance mutants; no judge or model invocation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

CHANGES = {
    "rounding": (
        ".divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)",
        '.divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN).add(new BigDecimal("0.01"))',
    ),
    "skipped": (
        "new ArrayList<>(accountById.values()), generated",
        "new ArrayList<>(accountById.values()).subList(1, accountById.size()), generated",
    ),
    "date": ('                    timestamp,', '                    "2022-07-19-00.00.00.000000",'),
}
CLASS = "ai/lightyear/carddemo/service/InterestCalculationService.class"


def mutate(text, name):
    old, new = CHANGES[name]
    if text.count(old) != (2 if name == "date" else 1):
        raise ValueError(f"Unexpected acceptance mutation anchor count: {name}")
    return text.replace(old, new)


def build(workspace):
    project = workspace / "candidate-java"
    jar = project / "target/carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"
    original = project / "src/main/java/ai/lightyear/carddemo/service/InterestCalculationService.java"
    raw = jar.read_bytes()
    (workspace / "good.jar").write_bytes(raw)
    for name in CHANGES:
        with tempfile.TemporaryDirectory(prefix="verify-mutant-") as tmp:
            scratch = Path(tmp)
            source = scratch / original.name
            source.write_text(mutate(original.read_text(encoding="utf-8"), name), encoding="utf-8")
            annotation = scratch / "Service.java"
            annotation.write_text("package org.springframework.stereotype; @java.lang.annotation.Retention(java.lang.annotation.RetentionPolicy.RUNTIME) public @interface Service {}", encoding="utf-8")
            subprocess.run(["javac", "--release", "17", "-cp", str(project / "target/classes"),
                            "-d", str(scratch), str(annotation), str(source)], check=True)
            with zipfile.ZipFile(jar) as src, zipfile.ZipFile(workspace / f"{name}.jar", "w") as out:
                if src.namelist().count("BOOT-INF/classes/" + CLASS) != 1:
                    raise ValueError("Expected one Spring Boot service class")
                for info in src.infolist():
                    data = (scratch / CLASS).read_bytes() if info.filename == "BOOT-INF/classes/" + CLASS else src.read(info)
                    out.writestr(info, data)
    report = {"schema": "verify-smoke-candidates/1", "model_calls": 0,
              "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
              "jars": {f"{n}.jar": hashlib.sha256((workspace / f"{n}.jar").read_bytes()).hexdigest()
                       for n in ("good", *CHANGES)}}
    (workspace / "candidates.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
