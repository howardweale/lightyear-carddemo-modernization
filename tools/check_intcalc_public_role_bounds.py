"""CI test with hash-pinned PUBLIC context. No credentials, provider, oracle or Docker."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from lightyear_factory import intcalc_preview_composition as c
from test_intcalc_preview_composition import FakePorts, packet

def check(archive, allowlist):
    assert c.digest(archive)==c.CONTEXT_HASH and c.digest(allowlist)==c.ALLOWLIST_HASH
    context=c.context_members(archive,allowlist)
    expected={"ascii":[85867,94352,164225,172579],"escaped":[85867,118928,397697,430627]}
    rows=[]
    for mode,char in (("ascii","a"),("escaped",'"')):
        artifacts={}
        for i,role in enumerate(c.ROLES):
            field="source" if role.startswith("builder") else "text"
            feedback=None if i<2 else dict(schema=c.COMPILE_SCHEMA,kind="compilation-failed",javac_stderr=char*4096,stderr_truncated=False)
            if feedback is not None:c.validate_feedback(feedback)
            bound_packet=packet()
            bound_packet.update(context_sha256=c.CONTEXT_HASH,allowlist_sha256=c.ALLOWLIST_HASH)
            ports=FakePorts()
            session=c.Composition(bound_packet,archive,allowlist,ports,clock=lambda:ports.now)
            session._artifacts=json.loads(c.canonical(artifacts))
            session._admission=SimpleNamespace(deadline_monotonic=ports.now+8100)
            session._transport=ports
            projection=dict(model=c.MODEL,instructions=c.ROLE_INSTRUCTIONS[role],
                input=c.canonical(dict(public_context=context,generated_artifacts=artifacts,feedback=feedback)).decode(),
                text=dict(format=dict(type="json_schema",name="c2_artifact",strict=True,schema=session._schema(role))))
            bound=len(c.canonical(projection))+4096
            assert bound==expected[mode][i]
            if role=="planner":assert bound<=85876
            if bound<=c.ROLE_INPUT_CAPS[role]:
                session._send(role,feedback)
                assert c.canonical(ports.projections[role])==c.canonical(projection)
            else:
                try:session._send(role,feedback)
                except c.CompositionRefused as error:assert str(error)=="budget-fixed-input-cap"
                else:raise AssertionError("expected pre-count refusal")
                assert session._holds==0 and ports.events==[] and ports.records=={}
            rows.append(dict(role=role,shape=mode,bound=bound,cap=c.ROLE_INPUT_CAPS[role],fits=bound<=c.ROLE_INPUT_CAPS[role]))
            artifacts[role]={field:char*(65536 if field=="source" else 8192)}
    print(json.dumps(dict(public_context_bounds="MATCH",rows=rows)))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",required=True);parser.add_argument("--allowlist",required=True)
    args=parser.parse_args()
    check(Path(args.archive).read_bytes(),Path(args.allowlist).read_bytes())
