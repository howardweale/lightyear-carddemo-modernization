"""Pinned two-view public capture comparison. No database or model execution."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIEWS = ("customer_list", "sales_by_store")
VARIANTS = ("original", "active-flip", "payment-omission")


class InsufficientEvidence(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InsufficientEvidence("duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(raw, parse_float=Decimal, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              InsufficientEvidence("nonfinite JSON number")))
    except (ValueError, TypeError) as exc:
        raise InsufficientEvidence("invalid capture JSON") from exc


def configuration():
    manifest_raw = (ROOT/"manifest.json").read_bytes()
    manifest = loads(manifest_raw)
    for relative, expected in manifest["files"].items():
        path = ROOT.parent.parent/relative
        if sha(path.read_bytes()) != expected:
            raise InsufficientEvidence("pinned input changed: "+relative)
    return manifest, sha(manifest_raw), loads((ROOT/"contract.json").read_bytes())


def extract_views(destination):
    """Materialize exact upstream SQL only; no database execution."""
    manifest, _, _ = configuration()
    destination = Path(destination)
    if not destination.is_dir():
        raise InsufficientEvidence("existing empty output directory required")
    if any(destination.iterdir()):
        raise InsufficientEvidence("refuse nonempty output directory")
    for relative, metadata in manifest["views"].items():
        record = loads((ROOT.parent.parent/relative).read_bytes())
        import base64
        raw = base64.b64decode(record["sql_base64"], validate=True)
        if sha(raw) != metadata["view_sha256"] or sha(raw) != record["sha256"] or len(raw) != record["bytes"]:
            raise InsufficientEvidence("preserved view bytes mismatch")
        with (destination/Path(relative).name.removesuffix(".json")).open("xb") as output:
            output.write(raw)


def assemble(engine, image, version, variant, observations, *, manifest=None, manifest_sha=None):
    if manifest is None:
        manifest, manifest_sha, _ = configuration()
    if (engine not in ("sqlserver", "postgres") or variant not in VARIANTS
            or image != manifest["engines"][engine]["image"]
            or type(version) is not str or not version.strip()
            or set(observations) != set(VIEWS)):
        raise InsufficientEvidence("missing engine identity, variant or view")
    return dict(schema="sakila-public-capture/1", engine=engine, image=image,
                engine_version=version, variant=variant, manifest_sha256=manifest_sha,
                status="captured", views=observations,
                provenance="caller-supplied-capture; CI/raw-byte retention required")


def _decimal(value):
    if type(value) not in (str, int, Decimal):
        raise InsufficientEvidence("decimal requires exact JSON decimal or string")
    try:
        number = Decimal(value)
        if not number.is_finite() or abs(number) > Decimal("999999999999"):
            raise InsufficientEvidence("unsupported decimal")
        fixed = number.quantize(Decimal("0.01"))
        if fixed != number:
            raise InsufficientEvidence("decimal scale outside contract")
        return format(fixed, ".2f")
    except (InvalidOperation, ValueError) as exc:
        raise InsufficientEvidence("invalid decimal") from exc


def _rows(capture, view, contract):
    engine = capture["engine"]
    observation = capture["views"][view]
    if type(observation) is not dict or set(observation) != {"columns", "rows"}:
        raise InsufficientEvidence("missing catalog or row capture")
    columns, rows = observation["columns"], observation["rows"]
    if (type(columns) is not list or not columns
            or any(type(c) is not dict or set(c) != {"name", "type"}
                   or type(c["name"]) is not str or type(c["type"]) is not str for c in columns)):
        raise InsufficientEvidence("invalid catalog")
    names = [c["name"] for c in columns]
    mapped = contract["mapping"][view][engine]
    expected = (["store_id"]+mapped if view == "sales_by_store" and engine == "sqlserver" else mapped)
    if names != expected:
        raise InsufficientEvidence("unexpected original column names/order")
    if type(rows) is not list or len(rows) != 2:
        raise InsufficientEvidence("incomplete fixture rows")
    normalized = []
    for row in rows:
        if type(row) is not dict or set(row) != set(names):
            raise InsufficientEvidence("missing/extra row fields")
        values = []
        for index, name in enumerate(mapped):
            value = row[name]
            if view == "customer_list" and index in (0, 8):
                if type(value) is not int:
                    raise InsufficientEvidence("integer mapping")
            elif view == "sales_by_store" and name == "total_sales":
                value = _decimal(value)
            elif value is not None and type(value) is not str:
                raise InsufficientEvidence("text mapping")
            values.append(value)
        normalized.append(json.dumps(values, ensure_ascii=False, separators=(",", ":")))
    if view == "customer_list" and {row[mapped[0]] for row in rows} != {1, 2}:
        raise InsufficientEvidence("fixture customer identities")
    if view == "sales_by_store" and engine == "sqlserver":
        if {row["store_id"] for row in rows} != {1, 2}:
            raise InsufficientEvidence("fixture store identities")
    return Counter(normalized), columns


def compare(left, right, *, manifest=None, manifest_sha=None, contract=None,
            expected_right_variant="original"):
    """Common-field MATCH is separate from strict schema and control evidence."""
    try:
        if manifest is None:
            manifest, manifest_sha, contract = configuration()
        for capture, engine, variant in ((left, "sqlserver", "original"),
                                         (right, "postgres", expected_right_variant)):
            if (type(capture) is not dict or capture.get("schema") != "sakila-public-capture/1"
                    or capture.get("status") != "captured" or capture.get("engine") != engine
                    or capture.get("variant") != variant or variant not in VARIANTS
                    or capture.get("manifest_sha256") != manifest_sha
                    or capture.get("image") != manifest["engines"][engine]["image"]
                    or type(capture.get("engine_version")) is not str
                    or not capture["engine_version"].strip()
                    or type(capture.get("views")) is not dict or set(capture["views"]) != set(VIEWS)):
                raise InsufficientEvidence("missing/failed/unbound capture")
        result = {}
        for view in VIEWS:
            a, a_columns = _rows(left, view, contract)
            b, b_columns = _rows(right, view, contract)
            result[view] = dict(
                strict_schema="MATCH" if a_columns == b_columns else "DIFFERENT",
                original_sqlserver_columns=a_columns, original_postgres_columns=b_columns,
                common_fields="MATCH" if a == b else "DIFFERENT",
                only_sqlserver=list((a-b).elements()), only_postgres=list((b-a).elements()))
        return dict(status="COMPARED", views=result, right_variant=expected_right_variant,
                    native_or_customer_qualification=False,
                    sensitivity_controls="NOT_OBSERVED" if expected_right_variant == "original"
                    else "VERIFIER_AUTHORED_CONTROL_COMPARISON")
    except (InsufficientEvidence, KeyError, TypeError, OSError) as exc:
        return dict(status="INSUFFICIENT_EVIDENCE", reason=str(exc),
                    native_or_customer_qualification=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("destination")
    capture = sub.add_parser("assemble")
    for name in ("engine", "image", "version", "variant", "customer", "sales", "output"):
        capture.add_argument("--"+name, required=True)
    comparison = sub.add_parser("compare")
    comparison.add_argument("sqlserver")
    comparison.add_argument("postgres")
    comparison.add_argument("--right-variant", choices=VARIANTS, default="original")
    args = parser.parse_args()
    if args.command == "extract":
        extract_views(args.destination)
        return
    if args.command == "assemble":
        observations = {view: loads(Path(path).read_bytes()) for view, path in
                        (("customer_list", args.customer), ("sales_by_store", args.sales))}
        result = assemble(args.engine, args.image, args.version, args.variant, observations)
        with Path(args.output).open("x", encoding="utf-8") as output:
            json.dump(result, output, default=str, ensure_ascii=False, indent=2)
    else:
        try:
            result = compare(loads(Path(args.sqlserver).read_bytes()),
                             loads(Path(args.postgres).read_bytes()),
                             expected_right_variant=args.right_variant)
        except (OSError, InsufficientEvidence) as exc:
            result = dict(status="INSUFFICIENT_EVIDENCE", reason=str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "COMPARED":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
