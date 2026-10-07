"""Operator-only projection and judge-side leak scan. Never imported by toolkit."""
import gzip
import json
import re
from collections import Counter
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest
from lightyear_mainframe.zos_evidence import confined
from lightyear_toolkit.graph_approval import sha


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, path + "/" + k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, path + "/" + str(i))


def tainted(value):
    forbidden = ("inspector_private", "runtime", "reference-data", "reference_data",
                 "holdout", "expected_value", "capture", "oracle", "test_case")
    if isinstance(value, dict):
        if any(k.lower() in {"inspector_private", "runtime_capture", "reference_data", "holdout"}
               and v not in (None, False, "") for k, v in value.items()):
            return True
        if any(tainted(v) for v in value.values() if isinstance(v, (dict, list))):
            return True
    elif isinstance(value, list) and any(tainted(v) for v in value):
        return True
    return any(any(word in text.lower() for word in forbidden)
               for path, text in strings(value)
               if any(k in path.lower() for k in
                      ("provenance", "visibility", "audience", "method", "origin", "source", "kind")))


def watch_values(evaluation, lane_id):
    """Decode every declared input/output record with its existing lane binding."""
    from lightyear_mainframe.records import load_copybook, decode_fixed, decode_rdw
    from lightyear_mainframe.zos_bindings import ROOT, load_bindings, dataset_binding
    bindings = load_bindings()
    result = set()
    runs = sorted(Path(evaluation).glob("*/run.json"))
    if not runs:
        raise ValueError("graph-evaluation-empty")
    for path in runs:
        meta = read(path)
        if meta["job"] != lane_id:
            raise ValueError("graph-evaluation-lane")
        for d in meta["datasets"]:
            binding = dataset_binding(bindings, meta["job"], d["step"], d["dd"])
            if not binding.get("copybook"):
                raise ValueError("graph-private-layout-unbound")
            raw = confined(path.parent, d["file"]).read_bytes()
            decoder = decode_rdw if d.get("framing") == "rdw" else decode_fixed
            for record in decoder(load_copybook(ROOT / binding["copybook"]), raw, codec=d["codec"]):
                for f in record["fields"]:
                    text = str(f["value"]).strip()
                    for token in [text, *re.findall(r"[A-Za-z0-9_./:+-]+", text)]:
                        digits = re.sub(r"\D", "", token).lstrip("0")
                        if len(token) >= 6 or len(digits) >= 4 or re.search(r"\d{4}[-/]\d\d[-/]\d\d", token):
                            result.add(token)
    return result


def source_bytes(lane, root):
    """Hash-verified public files, kept separate without text normalization."""
    output = {}
    if lane.get("public_fixture_only") is not True or lane["customer_id"] != "carddemo-reference":
        raise ValueError("graph-public-source-only")
    for key, item in lane["approved_sources"].items():
        raw = confined(root, item["file"]).read_bytes()
        if sha(raw) != item["sha256"]:
            raise ValueError("graph-approved-source-changed")
        output[key] = raw
    return output


def sources(lane, root):
    """Source excerpts use only the same hash-verified public bytes."""
    return {key: raw.decode("utf-8").splitlines()
            for key, raw in source_bytes(lane, root).items()}


def build(graph_path, evidence_path, policy_path, lane_id, mode, customer_id,
          out, signer, *, source_root, watch=(), annotation_ledger=None, hybrid=False, include_inferred=False,
          embedding_provider=None):
    out = Path(out)
    if out.exists():
        raise ValueError("graph-output-exists")
    policy, graph, evidence = map(read, (policy_path, graph_path, evidence_path))
    lane = policy["lanes"][lane_id]
    if mode not in {"field", "confidential"} or lane["customer_id"] != customer_id:
        raise ValueError("graph-lane-mode")
    approved = sources(lane, source_root)
    # Fail closed for a capsule carrying hidden/runtime provenance, even though
    # excerpts are taken from approved source, never from capsule text.
    bad_owners = {s["owner_id"] for c in evidence["capsules"] for s in c.get("supports", [])
                  if tainted(c) or s.get("visibility") == "inspector_private"}
    by_id = {n["id"]: n for n in graph["nodes"]}
    denied = {n["id"] for n in graph["nodes"] if tainted(n) or n["id"] in bad_owners
              or n["kind"] not in policy["node_properties"]}
    dependencies = {}
    for edge in graph["edges"]:
        if edge["relation"] in {"DERIVED_FROM", "BASED_ON", "OBSERVED_IN", "EVIDENCED_BY"}:
            dependencies.setdefault(edge["source"], []).append(edge["target"])
    # Explicit provenance dependencies are transitive; cycles/unknown references fail closed.
    def clean_chain(node, seen=frozenset()):
        if node["id"] in seen or node["id"] in denied:
            return False
        refs = (node.get("provenance_dependencies", []) +
                node.get("properties", {}).get("provenance_dependencies", []) +
                dependencies.get(node["id"], []))
        return all(r in by_id and clean_chain(by_id[r], seen | {node["id"]}) for r in refs)
    nodes, excluded = [], Counter()
    for n in graph["nodes"]:
        kind, props = n["kind"], n.get("properties", {})
        if kind not in policy["node_properties"]:
            excluded["node-kind"] += 1; continue
        if not clean_chain(n) or props.get("customer_id", customer_id) != customer_id:
            excluded["node-provenance-or-scope"] += 1; continue
        ev = n.get("evidence", [])
        if not ev or any(e.get("confidence") not in {"observed", "asserted"} or
                         e.get("method") not in policy["source_methods"] or
                         e["source_id"] + ":" + e["path"] not in approved for e in ev):
            excluded["unapproved-source"] += 1; continue
        if kind == "business_rule" and (props.get("confidence", ev[0]["confidence"]) != "observed"
                and n["id"] not in lane.get("reviewed_mapping_ids", [])):
            excluded["unreviewed-rule"] += 1; continue
        clean = {k: v for k, v in props.items() if k in policy["node_properties"][kind]
                 and isinstance(v, (str, int)) and not isinstance(v, bool)}
        excluded["property"] += len(props) - len(clean)
        clean["customer_id"] = customer_id
        clean["provenance"] = "observed" if all(e["confidence"] == "observed" for e in ev) else "asserted"
        excerpts = []
        for e in ev:
            key = e["source_id"] + ":" + e["path"]
            lines = approved[key]
            start = e["line_start"]
            if not isinstance(start, int) or not 1 <= start <= len(lines):
                raise ValueError("graph-source-range")
            # Paragraph graph evidence marks its header. Extend through the next
            # paragraph header, then cap; references use this approved source only.
            end = e["line_end"]
            if kind == "cobol_paragraph":
                headers = [x["line_start"] for p in graph["nodes"] if p["kind"] == kind
                    for x in p.get("evidence", []) if x["path"] == e["path"] and x["line_start"] > start]
                end = min(headers, default=len(lines)+1)-1
            end = min(end, start+119, len(lines))
            item = dict(path=e["path"], line_start=start, line_end=end)
            if mode == "field" or key in lane["program_sources"]:
                text = "\n".join(lines[start-1:end])
                if mode == "confidential":
                    # Redact ALL literals, not a private-data-dependent subset.
                    # Otherwise redaction positions themselves disclose watch-list membership.
                    text = re.sub(r"""'[^']*'|"[^"]*"|(?<![\w-])[-+]?\d+(?:\.\d+)?(?![\w-])""",
                                  "[redacted]", text)
                item["text"] = text
            excerpts.append(item)
        if mode == "confidential":
            # Structure only; statements can smuggle non-source values.
            clean.pop("statement", None)
        nodes.append(dict(id=n["id"], kind=kind, name=n["name"], properties=clean, evidence=[],
                          source=excerpts))
    ids = {n["id"] for n in nodes}
    edges, verified = [], []
    for e in graph["edges"]:
        if tainted(e) or e["id"] in bad_owners:
            excluded["edge-provenance"] += 1; continue
        if e["relation"] == "VERIFIED_BY" and e["source"] in ids:
            # Only reviewed public scenario IDs; never include a scenario node/body.
            if e["target"] in lane.get("public_scenario_ids", []):
                verified.append(dict(source=e["source"], relation="VERIFIED_BY", target=e["target"]))
            continue
        ev=e.get("evidence",[])
        if not ev or any(x.get("confidence") not in {"observed","asserted"} or
                x.get("method") not in policy["source_methods"] or
                x["source_id"]+":"+x["path"] not in approved for x in ev):
            excluded["edge-unapproved-source"] += 1; continue
        if e["relation"] not in policy["relations"] or e["source"] not in ids or e["target"] not in ids:
            excluded["edge-kind-or-endpoint"] += 1; continue
        edges.append(dict(id=e["id"], source=e["source"], target=e["target"],
                          relation=e["relation"], properties={}, evidence=[]))
    projection = dict(schema="verify-graph-projection/1", lane=lane_id, mode=mode,
        customer_id=customer_id, lane_sha256=digest(lane),
        nodes=sorted(nodes, key=lambda n:n["id"]), edges=sorted(edges,key=lambda e:e["id"]),
        verified_by=sorted(verified,key=lambda e:(e["source"],e["target"])),
        dataset_copybooks=lane.get("dataset_copybooks", {}),
        dataset_file_names=lane.get("dataset_file_names", {}))
    extensions = {}
    if annotation_ledger is not None:
        from lightyear_factory.annotations import retrieve
        states = annotation_ledger.replay()
        # Only approved, non-expired, unflagged records on included public anchors.
        rows = retrieve(states, ids, edges, customer_id, cap=4*1024*1024, include_inferred=include_inferred)["items"]
        rows = [a for a in rows if set(a["anchors"]) <= ids]
        if any(tainted(a) or any(v and v in canonical(a).decode() for v in watch) for a in rows):
            raise ValueError("annotation projection leak")
        projection["annotations"] = rows
        from lightyear_factory.revocations import binding
        projection['revocation_binding']=binding(annotation_ledger)
        extensions["annotation_ledger_sha256"] = sha(annotation_ledger.path.read_bytes())
    if hybrid:
        from lightyear_knowledge_graph.hybrid import build_index
        projection["search_index"] = build_index(projection,embedding_provider)
        extensions["search_index_sha256"] = projection["search_index"]["content_sha256"]
        extensions["embedding_provider"] = projection["search_index"]["provider"]
    packed = gzip.compress(canonical(projection), mtime=0)
    manifest = signer.sign(dict(schema="verify-graph-manifest/1", lane=lane_id, mode=mode,
        customer_id=customer_id, lane_sha256=digest(lane), projection_sha256=sha(packed),
        graph_sha256=sha(Path(graph_path).read_bytes()), evidence_sha256=sha(Path(evidence_path).read_bytes()),
        policy_sha256=sha(Path(policy_path).read_bytes()),
        included_kinds=dict(sorted(Counter(n["kind"] for n in nodes).items())),
        included_relations=dict(sorted(Counter(e["relation"] for e in edges+verified).items())),
        excluded=dict(sorted(excluded.items())), model_calls=0, **extensions))
    out.mkdir(parents=True)
    (out/"projection.json.gz").write_bytes(packed)
    (out/"projection-manifest.json").write_bytes(canonical(manifest))
    return manifest


def leak_check(directory, lane_hash, watch, signer, *, evaluation_inventory_sha256, approved_source=""):
    root = Path(directory)
    if not re.fullmatch(r"[a-f0-9]{64}", evaluation_inventory_sha256):
        raise ValueError("graph-evaluation-inventory")
    if (root/"leak-check.json").exists() or (root/"graph-leak-certificate.json").exists():
        raise ValueError("graph-leak-record-exists")
    raw = (root/"projection.json.gz").read_bytes()
    projection = read(root/"projection.json.gz")
    if projection["lane_sha256"] != lane_hash:
        raise ValueError("graph-leak-lane")
    # A public overlap need not be quoted. Preserve exact case/bytes and file
    # boundaries; concatenation could invent a match not present in any file.
    public_files = (approved_source,) if isinstance(approved_source, (str, bytes)) else tuple(approved_source)
    public_files = tuple(s.encode("utf-8") if isinstance(s, str) else s for s in public_files)
    matches = []
    for path, text in strings(projection):
        for value in sorted(watch):
            if value and value in text:
                # IDs/property locations can themselves contain protected strings:
                # never echo arbitrary graph identifiers into the safe report.
                parts=path.split("/")
                node_id=projection["nodes"][int(parts[2])]["id"] if len(parts)>2 and parts[1]=="nodes" else "$projection"
                safe=lambda text: "sha256:"+sha(text.encode()) if any(v in text for v in watch) else text
                matches.append(dict(node_id=safe(node_id), property=safe(path),
                    location_sha256=sha(path.encode()), value_sha256=sha(value.encode()),
                    classification="source-literal" if any(value.encode("utf-8") in source for source in public_files) else "protected"))
    report = signer.sign(dict(schema="verify-graph-leak/1", projection_sha256=sha(raw),
        evaluation_inventory_sha256=evaluation_inventory_sha256,
        lane_sha256=lane_hash, watch_list_size=len(watch), matches=matches,
        passed=not matches, model_calls=0))
    (root/"leak-check.json").write_bytes(canonical(report))
    # The detailed watch-list count/match locations stay on the judge side.
    # Agent admission needs only the report binding and public-source exceptions.
    certificate = signer.sign(dict(schema="verify-graph-leak-certificate/1",
        evaluation_inventory_sha256=evaluation_inventory_sha256,
        report_sha256=sha(canonical(report)), projection_sha256=sha(raw), lane_sha256=lane_hash,
        eligible=not any(m["classification"]!="source-literal" for m in matches),
        source_literal_exceptions=sorted({m["value_sha256"] for m in matches if m["classification"]=="source-literal"})))
    (root/"graph-leak-certificate.json").write_bytes(canonical(certificate))
    return report
