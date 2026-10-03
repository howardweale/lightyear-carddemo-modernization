"""Independent calendar/input/runtime audit of actual native captures."""
from datetime import datetime, timezone
import json
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.native_reconciliation import state, rows
from tools.ms94_calendar import guard, instant, DATE

TABLES=('c_order','m_inventory','m_inout','c_invoice','c_payment','c_allocationhdr','fact_acct')
FIELDS=('dateacct','datetrx','dateordered','datepromised','dateinvoiced','movementdate','shipdate')

def date_time(value):
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)

def audit_dates(before_folder,after_folder,lane,calendar):
    before=state(before_folder,lane);after=state(after_folder,lane)
    low=instant(calendar['period_start_utc']);high=instant(calendar['period_end_exclusive_utc'])
    checked={}
    for table in TABLES:
        require(table in before['tables'] and table in after['tables'],'Date-audit table missing')
        key=table+'_id';old={r[key] for r in rows(before_folder,before['tables'][table])}
        new=[r for r in rows(after_folder,after['tables'][table]) if r[key] not in old]
        fields={}
        for row in new:
            for field in FIELDS:
                if row.get(field) is not None:
                    require(low<=date_time(row[field])<high,'New journey date outside frozen accounting period: '+table+'.'+field)
                    fields[field]=fields.get(field,0)+1
        checked[table]={'new_records':len(new),'date_fields_checked':fields}
    return checked

def replay_calendar(run):
    plan=read_json(run/'plan.json');verify(plan);calendar=plan['calendar'];verify(calendar)
    source=(run/'inputs/operations.java').read_bytes()
    require(set(DATE.findall(source))=={calendar['scenario_date'].encode()},'Source date differs from declared calendar')
    entries=[json.loads(line) for line in (run/'calendar-guards.jsonl').read_bytes().splitlines()]
    require(entries and entries[-1]['stage']=='pair-complete','Pair did not complete within the calendar guard')
    previous=None
    for item in entries:
        require(item['calendar_sha256']==calendar['content_sha256'],'Guard calendar differs')
        now=instant(item['real_utc']);guard(calendar,now)
        require(previous is None or now>=previous,'Real UTC moved backwards')
        previous=now
    runtime=read_json(run/'real-time-containers.json')
    expected={plan['local']['runner_image'],*[v['image_digest'] for v in plan['declaration']['environment']['engines'].values()]}
    require(len(runtime)==5 and len({v['container'] for v in runtime})==5,'Missing native runtime attestations')
    require(all(v['image'] in expected and v['clock_manipulation_environment'] is False
                and not v['privileged'] and not v['sys_time_capability'] for v in runtime),'Runtime clock isolation differs')
    result={}
    for lane in ('oracle','postgresql'):
        execution=read_json(run/'cases/operations/1/execution'/lane/'execution.json');verify(execution)
        for name in ('native_clock_before','native_clock_after'):
            value=execution[name]['value']
            observed=date_time(value)
            require(instant(calendar['period_start_utc'])<=observed<instant(calendar['period_end_exclusive_utc']),
                    'Native database real clock outside accounting period')
            require(date_time(entries[0]['real_utc']).timestamp()-5<=observed.timestamp()<=previous.timestamp()+5,
                    'Native clock outside real host execution window')
        result[lane]={'native_clock_before':execution['native_clock_before']['value'],
                      'native_clock_after':execution['native_clock_after']['value'],
                      'new_document_and_posting_dates':audit_dates(run/'cases/operations/1/baseline'/lane/'after',
                            run/'cases/operations/1/after'/lane,lane,calendar)}
    return {'calendar_sha256':calendar['content_sha256'],'guards_replayed':len(entries),
            'real_time_container_attestations':len(runtime),'lanes':result,'passed':True}
