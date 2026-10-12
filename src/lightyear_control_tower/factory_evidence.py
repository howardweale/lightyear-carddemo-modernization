"""Hash-bound public Factory read model. No runs, decisions or filesystem writes."""
from collections import Counter
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from .decisions import canonical, digest
from .requests import read_json, read_bytes, confined, SHA
from .factory_policy import require, load_contract, FactoryDecisions
from .presentation import FACTORY_FILES, FACTORY_SUMMARY_FIELDS, FACTORY_MUTANT_FIELDS, FACTORY_REGISTER_FIELDS, FACTORY_THRESHOLD_FIELDS

INDEX = "work/control-tower/factory-evidence-index.json"
PROGRAMS = {"INTCALC": "CBACT04C", "POSTTRAN": "CBTRN02C"}


def take(value, keys):
    return {k:value[k] for k in keys if k in value}


class FactoryEvidence:
    def __init__(self, root, expected_index_sha256):
        require(isinstance(expected_index_sha256,str) and SHA.fullmatch(expected_index_sha256), "factory-index-trust-required")
        self.root = Path(root)
        path = confined(root, INDEX, internal=True)
        require(sha256(read_bytes(path)).hexdigest() == expected_index_sha256, "factory-index-hash")
        self.index = read_json(path)
        require(set(self.index) == {"schema", "commit", "created_at", "sources"} and self.index["schema"] == "factory-evidence-index/1")
        require(len(self.index["commit"]) == 40 and all(c in "0123456789abcdef" for c in self.index["commit"]))
        self.sources = {}
        for source in self.index["sources"]:
            require(set(source) == {"path", "sha256"})
            name = source["path"].removeprefix("docs/factory/")
            require(source["path"] == "docs/factory/"+name and name in FACTORY_FILES and name not in self.sources, "factory-adapter-not-allowed")
            require(isinstance(source["sha256"],str) and SHA.fullmatch(source["sha256"]))
            self.sources[name] = {**source, "commit":self.index["commit"]}
        require(set(self.sources) == set(FACTORY_FILES), "factory-evidence-inventory-incomplete")
        self.sha256 = expected_index_sha256

    def read(self, name):
        source = self.sources[name]
        path = confined(self.root, source["path"])
        raw = read_bytes(path)
        require(sha256(raw).hexdigest() == source["sha256"], "factory-evidence-hash")
        return raw.decode("utf-8") if FACTORY_FILES[name] is None else take(read_json(path), FACTORY_FILES[name])

    def block(self, value, *names):
        return dict(value=value, sources=[self.sources[n] for n in names])

    def program(self, program, *, overlays=(), pending=()):
        require(program in PROGRAMS, "factory-program-not-found")
        name="systematic-"+program.lower()+"-review311.json"
        data=self.read(name)
        summary=take(data["summary"], FACTORY_SUMMARY_FIELDS)
        mutants=[take(r,FACTORY_MUTANT_FIELDS) for r in data["mutants"]]
        policy=self.read("tower-display-policy.json")
        checklist=[]
        coverage=summary.get("after_faults",{}).get("coverage_by_class",{})
        business=coverage.get("business-logic",{}).get("fraction")
        def criterion(label,value,state,reason):
            checklist.append(dict(criterion=label,value=value,state=state,reason=reason,
                sources=[self.sources[name],self.sources["tower-display-policy.json"]]))
        criterion("Business outcomes",business,"not reported" if business is None else "met" if Fraction(business)>=Fraction(policy["business_logic_outcomes"]) else "failed", "Measured business-logic coverage only")
        gaps=summary.get("after_faults",{}).get("uncovered",[])
        accepted={(x["details"]["outcome_id"],x["details"]["outcome"]) for x in overlays
            if x["kind"]=="io-exception-acceptance" and x["outcome"]=="accept" and x["details"]["source_sha256"]==summary["source_sha256"]}
        remaining=[g for g in gaps if (g.get("id"),g.get("outcome")) not in accepted]
        criterion("I/O outcomes",coverage.get("io-handling",{}).get("fraction"),"pending" if remaining else "met", "Gaps require exact signed exceptions; chat records are historical")
        criterion("Mutation adequacy",None,"not reported","Historical classifier results are not current refusal-corrected kill evidence; import a reviewed fresh receipt before a threshold claim")
        criterion("Systematic set",summary.get("mutant_count"),"met" if summary.get("mutant_count",0)>=policy["minimum_systematic_mutants"] else "failed", "Generated count; exclusions still require verification")
        criterion("Output diversity",None,"not reported","This compact historical receipt does not contain the compared-field diversity inventory")
        signed_policy=[x for x in overlays if x["kind"]=="scenario-threshold-approval" and x["outcome"]=="approve" and x["details"]["policy_sha256"]==digest(policy)]
        criterion("Effective signed policy",policy["schema"],"met" if signed_policy and signed_policy[-1]["details"]["effective_condition"]=="unconditional" else "pending","A conditional or unsigned policy is not effective")
        resolved=set()
        for x in overlays:
            if x["kind"]=="equivalence-review" and x["outcome"]=="accept" and x["details"]["packet_sha256"]==self.sources[name]["sha256"]:
                resolved.update(x["details"]["items"])
        equivalent=[r for r in mutants if r.get("status")=="equivalent (argued, listed)"]
        classes=[]
        for kind in sorted({r.get("operator","unclassified") for r in equivalent}):
            members=[r for r in equivalent if r.get("operator","unclassified")==kind]
            classes.append(dict(class_name=kind,count=len(members),accepted=sum(r["id"] in resolved for r in members),
                                resolution="signed review" if all(r["id"] in resolved for r in members) else "review pending"))
        register=self.read("keep-or-fix-register.json")
        entries=[take(r,FACTORY_REGISTER_FIELDS) for r in register["defects"] if r["program"]==PROGRAMS[program]]
        for row in entries:
            row["signed_overlay"]=[x for x in overlays if x["kind"]=="legacy-behaviour-disposition" and x["details"]["entry_id"]==row["id"] and x["details"]["source_sha256"]==row["source_sha256"]]
        twin=self.read("gnucobol-twin-result.json")
        # Read limits bytes even when rendering only their fixed public link.
        limits=self.read("twin-limits.md")
        answer=dict(**twin, oracle_status="provisional", limits=limits,
                    review_state="pending", spend_state="not reported")
        answer_sources=["gnucobol-twin-result.json","twin-limits.md"]
        if program=="POSTTRAN":
            review=self.read("posttran-decisions-unsigned-2026-10-11.json")
            answer["unsigned_review_count"]=len(review["decisions"])
            answer["review_state"]="signed" if any(x["kind"]=="twin-human-review" and x["outcome"]=="accept" and x["details"]["sheet_sha256"]==review["sheet_sha256"] for x in overlays) else "unsigned review received; signature pending"
            answer["second_opinion"]=self.read("posttran-second-opinion/attempt-1-public-summary-2026-10-11.json")
            answer_sources += ["posttran-decisions-unsigned-2026-10-11.json", "posttran-second-opinion/attempt-1-public-summary-2026-10-11.json"]
        view = dict(id=program,available=True,disclosure="public-development",evidence_commit=self.index["commit"],
            index_sha256=self.sha256,releasable=False,claim="Operator evidence view; no release or independent attestation",
            checklist=checklist,
            scenarios=self.block(dict(public_data=summary.get("before_faults"),with_declared_faults=summary.get("after_faults"),
                fault_count=summary.get("fault_count"),fault_expectations_met=summary.get("fault_expectations_met"),gaps=remaining),name),
            mutation=self.block(dict(historical=True,warning="Archived pre-correction classifier figures. Execution refusals are not authenticated kills. These are not current threshold results.",
                raw_counts=summary.get("mutation_counts"),raw_kill_fraction=summary.get("kill_rate"),
                after_exclusion_fraction=summary.get("eligible_kill_rate"),current_raw_kills=None,current_eligible_fraction=None,
                classes=classes,compiler_refusals=summary.get("not_compiled",[]),survivors=summary.get("unresolved_survivors",[])),name),
            answer_key=self.block(answer,*answer_sources),keep_or_fix=self.block(entries,"keep-or-fix-register.json"),
            waiting_on_you=dict(count=len(pending),items=list(pending)),decision_overlays=list(overlays))


        # Fresh compact receipts supersede only the display, never the archived
        # mutant records. The experiment head remains distinct from the UI commit.
        prefix="tower-run-38198096890/"+program+"/"
        fresh=self.read(prefix+"fresh.json")
        followup=self.read(prefix+"summary.json")
        scopes={k:take(v,FACTORY_THRESHOLD_FIELDS) for k,v in self.read(prefix+"threshold.json").items()}
        require(fresh["campaign_head"] == followup["current_head"] == scopes["twin"]["current_head"] == scopes["zos-facing"]["current_head"], "factory-run-head-binding")
        counts=fresh["mutation_counts"]
        kills=counts.get("killed-failure",0)+counts.get("killed-divergent",0)
        require(sum(counts.values())==fresh["mutant_count"] and fresh["kill_rate"]==f"{kills}/{fresh['mutant_count']}", "factory-raw-count-binding")
        for scope, row in scopes.items():
            m=row["mutation"]
            require(m["killed"]==kills and m["sites"]==fresh["mutant_count"] and m["kill_rate"]==f"{kills}/{m['eligible']}", "factory-scope-denominator-binding")
            require(m["eligible"]==m["sites"]-len(m["excluded_equivalents"])-len(m["compiler_refusals"]), "factory-scope-exclusions")
        view["observed_head"]=fresh["campaign_head"]
        view["mutation"]=self.block(dict(historical=False,raw_counts=counts,raw_kill_fraction=fresh["kill_rate"],
            classes=followup["disposition_counts"],compiler_scope=followup["compiler_scope"],
            compiler_refusals=fresh["not_compiled"],generator_avoided=fresh["generator_avoided_count"],
            survivors=fresh["unresolved_survivors"],evidence_gap_ids=fresh["evidence_gap_ids"],
            scoped_assessments=scopes,resources=followup["resource_usage"],
            warning="CI scope assessments retain the historical operator-policy basis. Signed Factory reviews are separate overlays; neither these rates nor green CI authorize release. Evidence-gap counts overlap proof categories."),prefix+"fresh.json",prefix+"summary.json",prefix+"threshold.json")
        view["scenarios"]=self.block(dict(public_data=fresh["before_faults"],with_declared_faults=fresh["after_faults"],
            fault_count=fresh["fault_count"],fault_expectations_met=fresh["fault_expectations_met"],
            gaps=scopes["twin"]["accepted_uncovered_IO"]+scopes["twin"]["unaccepted_outcomes"],
            exception_state="Historical acceptance; signed Factory exception overlay required"),prefix+"fresh.json",prefix+"threshold.json")
        current=scopes["twin"]
        checklist.clear()
        criterion("Business outcomes",current["business"]["fraction"],"met" if Fraction(current["business"]["fraction"])>=Fraction(policy["business_logic_outcomes"]) else "failed","Fresh measured business coverage")
        criterion("I/O outcomes",current["io"]["fraction"],"pending" if current["accepted_uncovered_IO"] or current["unaccepted_outcomes"] else "met","Public and fault coverage; signed exact exceptions remain a separate gate")
        for scope,row in scopes.items():
            rate=row["mutation"]["kill_rate"]
            criterion("Mutation rate ("+scope+")",rate,"met" if Fraction(rate)>=Fraction(policy["legacy_mutants_killed"]) else "failed","Measured fraction under the CI assessment exclusions, not an effective Factory threshold approval")
        criterion("Systematic set",fresh["mutant_count"],"met" if fresh["mutant_count"]>=policy["minimum_systematic_mutants"] else "failed","Fresh generated sites; refusals are listed exclusions")
        criterion("Output diversity",str(len(current["below_two_values"]))+" fields below two values","failed" if current["below_two_values"] else "met","Measured across the exact compared-field inventory")
        criterion("Targeted evidence",len(current["mutation"]["targeted_evidence_gap_ids"]),"failed" if current["mutation"]["targeted_evidence_gap_ids"] else "met","Completed experiment still has missing comparisons")
        criterion("Effective signed policy",policy["schema"],"met" if signed_policy and signed_policy[-1]["details"]["effective_condition"]=="unconditional" else "pending","Requires the exact policy and completed signed reviews")
        for row in checklist: row["sources"]=[self.sources[prefix+"threshold.json"],self.sources[prefix+"fresh.json"],self.sources["tower-display-policy.json"]]
        view["answer_key"]["value"].update({k:fresh[k] for k in ("oracle_class","oracle_status","zos_confirmation")})
        view["answer_key"]["sources"].append(self.sources[prefix+"fresh.json"])
        return view


def for_service(service):
    if service.scope != "factory": return None
    path=service.authority_path.parent/"factory-evidence-trust.json"
    if not path.exists(): return None
    trust=read_json(path)
    require(set(trust)=={"schema","index_sha256"} and trust["schema"]=="factory-evidence-trust/1")
    return FactoryEvidence(service.root,trust["index_sha256"])


def decision_view(service, token):
    queue=service.queue(token)
    journal=service.export_session(token)
    reader=FactoryDecisions(service.public_key,journal["journal_head_sha256"])
    overlays=[];pending=[]
    for item in queue["items"]:
        if item.get("status")=="invalid":
            pending.append(dict(id=item["id"],program="factory",kind="invalid-request",source_sha256=journal["journal_head_sha256"]))
            continue
        contract=load_contract(service.root,item)
        latest=item.get("latest_decision")
        if latest:
            proof=service.proof(token,latest["content_sha256"])
            try:
                decision=reader.verify(proof,item["kind"],contract,service.registry.get(item["kind"]).outcomes)
                overlays.append(dict(kind=item["kind"],program=contract["program"],details=contract["details"],
                    outcome=decision["outcome"],source_sha256=latest["content_sha256"],journal_head_sha256=reader.head))
            except ValueError:
                pending.append(dict(id=item["id"],program=contract["program"],kind="invalidated-or-stale-review",source_sha256=item["bound"]["contract"]))
        else:
            pending.append(dict(id=item["id"],program=contract["program"],kind=item["kind"],
                created_at=item.get("created_at_utc"),source_sha256=item["bound"]["contract"]))
    return overlays,pending


def programs(service, token, program=None):
    evidence=for_service(service)
    if evidence is None: return dict(available=False,reason="Factory public evidence index not installed",programs=[])
    overlays,pending=decision_view(service,token)
    def one(name):
        return evidence.program(name,overlays=[x for x in overlays if x["program"] in {name,"factory"}],
            pending=[x for x in pending if x["program"] in {name,"factory"}])
    return one(program) if program else dict(available=True,programs=[one(n) for n in PROGRAMS])
