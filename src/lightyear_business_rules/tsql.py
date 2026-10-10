"""Five public procedure rules; replay saved signed captures, never start SQL."""
import json
from hashlib import sha256
from pathlib import Path
from lightyear_data.tsql_procedures.native_evidence import replay_pair, verify
from .language import require

PROCEDURES = {
    "len": ("LEN excludes trailing spaces: LEN(' A  ') returns 2.", "2"),
    "isnull-length": ("ISNULL retains the first argument's varchar(3) width, returning abc for the public NULL fallback.", "abc"),
    "money-scale": ("Conversion to money rounds the public 1.23456 input to four fractional digits, yielding 1.2346.", "1.2346"),
    "round-negative": ("ROUND(-150, -2) rounds the halfway value away from zero to -200.", "-200"),
    "datediff-day": ("DATEDIFF(day) counts crossed midnight boundaries; the public two adjacent timestamps yield 1.", "1"),
}


def mapping(root):
    root = Path(root)
    workloads=[]
    for name,(statement,value) in PROCEDURES.items():
        path=f"data-modernization/tsql-procedures/corpus/{name}/source.sql"
        node=f"legacy:tsql-procedure:{name}"
        output=node+":result:value"
        rule=dict(schema="lightyear-business-rule/1",id=f"rule:tsql:{name}",name=name,workload=f"workload:tsql:{name}",
            statement=statement, kind="calculation", inputs=[node], outputs=[output],
            bindings={"input.procedure":{"node":node},"output.value":{"node":output}},
            executable=dict(form="record_predicate",when={"op":"eq","args":[{"field":"input.procedure"},{"literal":name}]},
                condition={"op":"eq","args":[{"field":"output.value"},{"literal":value}]}),
            derived_from=[dict(node=node,path=path,line_start=2,line_end=7)],provenance="source-observed",confidence="observed",
            legacy_behaviour="faithful",decision_ref=None,implemented_by=[f"modern:tsql-procedure:{name}"],verified_by=[f"scenario:tsql-rule:{name}"])
        assets={}
        for variant in ("source","correct"):
            rel=f"data-modernization/tsql-procedures/corpus/{name}/{variant}.sql"
            assets[variant]=dict(path=rel,sha256=sha256((root/rel).read_bytes()).hexdigest())
        workloads.append(dict(id=rule["workload"],name=name,status="public-rule-fixture",source_language="T-SQL",
            source_assets=assets,legacy_entrypoints=[node],modern_entrypoints=[f"modern:tsql-procedure:{name}"],
            scenarios=[dict(id=f"scenario:tsql-rule:{name}",name="Historical public scalar capture",kind="captured-record-rule-check")],rules=[rule]))
    return dict(schema_version="1.0",workloads=workloads)


def capture_records(directory, root, trusted_key_sha256, expected_report_sha256):
    directory,root=Path(directory),Path(root)
    require("arrivals" not in directory.resolve().parts, "private-tsql-adapter-refused")
    public=(directory/"evidence-public-key.bin").read_bytes()
    require(sha256(public).hexdigest()==trusted_key_sha256,"tsql-recorder-key")
    report=json.loads((directory/"report.json").read_bytes())
    require(report["content_sha256"]==expected_report_sha256,"tsql-report-binding")
    verify(report,public)
    records={"source":[],"correct":[],"wrong":[]}
    bindings=[]
    for pair in sorted(directory.glob("pair-*")):
        manifest=json.loads((pair/"manifest.json").read_bytes())
        name=manifest["id"]
        if name not in PROCEDURES:continue
        require(sha256((pair/"manifest.json").read_bytes()).hexdigest()==report["files"][pair.name+"/manifest.json"],"tsql-report-file-binding")
        replay_pair(pair,public,manifest["content_sha256"])
        for variant in ("source",manifest["variant"]):
            asset=manifest["assets"][variant]
            require(asset["path"]==f"data-modernization/tsql-procedures/corpus/{name}/{variant}.sql" and
                    sha256((root/asset["path"]).read_bytes()).hexdigest()==asset["sha256"],"tsql-public-source-binding")
        for lane in ("source","target"):
            capture=json.loads((pair/(lane+".json")).read_bytes())
            obs=capture["observation"]
            require(obs["error"] is None and len(obs["result_sets"])==1 and len(obs["result_sets"][0]["rows"])==1,"tsql-scalar-result-required")
            values=obs["result_sets"][0]["rows"][0]
            require(len(values)==1 and isinstance(values[0],str),"tsql-result-type")
            variant="source" if lane=="source" else manifest["variant"]
            records[variant].append(dict(key=pair.name+"-"+lane,input={"procedure":name},output={"value":values[0]},
                meta={"pair_manifest_sha256":manifest["content_sha256"],"evidence_class":"signed-public-native-capture"}))
        bindings.append(manifest["content_sha256"])
    require(all({r["input"]["procedure"] for r in rows}==set(PROCEDURES) for rows in records.values()),"five-procedure-capture-required")
    return records,dict(report_sha256=expected_report_sha256,recorder_key_sha256=trusted_key_sha256,pair_manifests=bindings,
                        limitation="Historical public native scalar observations; no new databases or customer equivalence claim.")


def add_graph_nodes(graph, workload, root):
    from lightyear_knowledge_graph.model import evidence
    name=workload["name"]
    for variant,prefix in (("source","legacy"),("correct","modern")):
        asset=workload["source_assets"][variant]
        path=(Path(root)/asset["path"]).resolve()
        require(path.is_relative_to(Path(root).resolve()) and sha256(path.read_bytes()).hexdigest()==asset["sha256"],"tsql-graph-source-binding")
        node=f"{prefix}:tsql-procedure:{name}"
        ev=[evidence("source:lightyear-carddemo",asset["path"],2,7)]
        graph.add_node(node,"sql_procedure",name,properties=asset,evidence_items=ev)
        if variant=="source":
            graph.add_node(node+":result:value","sql_column","value",properties={"procedure":node},evidence_items=ev)
