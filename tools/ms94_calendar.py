"""Prospective UTC calendar-relative inputs; no application/database clock changes."""
from datetime import datetime, timedelta, timezone
import hashlib, json, re
from lightyear_calibration.contracts import canonical, require, seal, verify

DATE = re.compile(rb'(?<![0-9])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9])')

def utcnow(): return datetime.now(timezone.utc)

def instant(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.tzinfo is not None,'UTC instant requires timezone')
    return result.astimezone(timezone.utc)

def derive(now=None, maximum_seconds=16*3600):
    now=(now or utcnow()).astimezone(timezone.utc)
    require(type(maximum_seconds) is int and 0<maximum_seconds<=16*3600,'Invalid declared campaign duration')
    start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    value=seal({'policy':'utc-calendar-relative-scenario-v1','frozen_at_utc':now.isoformat(),
        'scenario_date':now.date().isoformat(),'period_start_utc':start.isoformat(),
        'period_end_exclusive_utc':end.isoformat(),'maximum_seconds':maximum_seconds,
        'clock_mode':'unmodified-real-time','date_mapping_rule':'Every builder-visible ISO calendar date maps to the UTC freeze date; time-of-day/fraction bytes are unchanged.',
        'pool_with_b03':False,'pooling_exclusion':'Prospective scenario date values differ from B03.'})
    guard(value,now);return value

def guard(calendar,now=None):
    verify(calendar);now=(now or utcnow()).astimezone(timezone.utc)
    require(calendar['clock_mode']=='unmodified-real-time','Clock manipulation forbidden')
    require(instant(calendar['period_start_utc'])<=now<instant(calendar['period_end_exclusive_utc']),
            'Real UTC is outside the frozen accounting period')
    require(now+timedelta(seconds=calendar['maximum_seconds'])<instant(calendar['period_end_exclusive_utc']),
            'Declared maximum campaign duration could cross accounting-period boundary')
    require(now>=instant(calendar['frozen_at_utc']),'Real UTC precedes input freeze')
    return now

def render(raw,calendar):
    """Byte transformation changes only ISO date substrings; no whitespace reserialization."""
    verify(calendar);target=calendar['scenario_date'].encode('ascii')
    for token in DATE.findall(raw):datetime.strptime(token.decode('ascii'),'%Y-%m-%d')
    return DATE.sub(lambda _:target,raw)

def projection(original,derived,calendar):
    require(render(original,calendar)==derived,'Inputs changed beyond declared dates')
    require(DATE.sub(b'<DATE>',original)==DATE.sub(b'<DATE>',derived),'Non-date bytes changed')
    return {'original_sha256':hashlib.sha256(original).hexdigest(),
        'rendered_sha256':hashlib.sha256(derived).hexdigest(),
        'original_dates':sorted({x.decode() for x in DATE.findall(original)}),
        'rendered_dates':sorted({x.decode() for x in DATE.findall(derived)}),
        'date_occurrences':len(DATE.findall(original)),'non_date_bytes_identical':True}

def public_prompt(root,calendar):
    from tools.ms94_controller_v5 import public_prompt as b03
    return json.loads(render(canonical(b03(root)),calendar))
