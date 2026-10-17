"""Five generated F0 calls; retain output hashes, never publish pricing bytes.

Public CMS software, independently tested. Generated source and rate adapters
remain under ignored work/cms. This is not an F1 general-purpose driver.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from tools.cms.f0_layout import layout
from tools.cms.f0_policy import diagnostic_metadata, require_smoke

PACKAGE = "files-fy-20215-software-release.zip"
PIN = "83aeeb51bab7f8410756f57504590d741f8d4c02c3db74bf8cce6b98886bc7af"
CLAIM = dict(providerCcn="B-21-PROVIDER-NO", coveredCharges="B-21-CHARGES-CLAIMED",
             coveredDays="B-21-COVERED-DAYS", diagnosisRelatedGroup="B-21-DRG",
             dischargeDate="B-21-DISCHARGE-DATE", lengthOfStay="B-21-LOS",
             lifetimeReserveDays="B-21-LTR-DAYS", reviewCode="B-21-REVIEW-CODE")
PROVIDER = dict(
    bedSize="P-NEW-BED-SIZE", bundleModel1Discount="P-MODEL1-BUNDLE-DISPRCNT",
    capitalCostToChargeRatio="P-NEW-CAPI-CSTCHG-RATIO",
    capitalExceptionPaymentRate="P-NEW-CAPI-EXCEPTIONS",
    capitalIndirectMedicalEducationRatio="P-NEW-CAPI-IME",
    costOfLivingAdjustment="P-NEW-COLA", hrrAdjustment="P-NEW-HOSP-HRR-ADJUSTMT",
    internsToBedsRatio="P-NEW-INTERN-RATIO", lowVolumeAdjustmentFactor="P-LV-ADJ-FACTOR",
    medicaidRatio="P-NEW-MEDICAID-RATIO", oldCapitalHoldHarmlessRate="P-NEW-CAPI-OLD-HARM-RATE",
    operatingCostToChargeRatio="P-NEW-CCR",
    passThroughAmountForDirectMedicalEducation="P-NEW-PASS-AMT-DIR-MED-ED",
    passThroughAmountForOrganAcquisition="P-NEW-PASS-AMT-ORGAN-ACQ",
    passThroughTotalAmount="P-NEW-PASS-AMT-PLUS-MISC",
    ppsFacilitySpecificRate="P-NEW-CMI-ADJ-CPD",
    supplementalSecurityIncomeRatio="P-NEW-SSI-RATIO", uncompensatedCareAmount="P-UNCOMP-CARE-AMOUNT",
    vbpAdjustment="P-NEW-VAL-BASED-PURCH-ADJUST", providerCcn="P-NEW-PROVIDER-NO",
    countyCode="P-NEW-COUNTY-CODE", effectiveDate="P-NEW-EFF-DATE",
    fiscalYearBeginDate="P-NEW-FY-BEGIN-DATE", providerType="P-NEW-PROVIDER-TYPE",
    stateCode="P-NEW-STATE-CODE", capitalPpsPaymentCode="P-NEW-CAPI-PPS-PAY-CODE",
    cbsaActualGeographicLocation="P-NEW-CBSA-GEO-LOC", cbsaWageIndexLocation="P-NEW-CBSA-RECLASS-LOC",
    cbsaStandardizedAmountLocation="P-NEW-CBSA-STAND-AMT-LOC",
    hospitalQualityIndicator="P-NEW-CBSA-HOSP-QUAL-IND",
    hrrParticipantIndicator="P-NEW-HOSP-READMISSION-REDU", hacReductionParticipantIndicator="P-HAC-REDUC-IND",
    vbpParticipantIndicator="P-NEW-VAL-BASED-PURCH-PARTIPNT", waiverIndicator="P-NEW-WAIVER-CODE",
    newHospital="P-NEW-CAPI-NEW-HOSP", supplementalWageIndexIndicator="P-NEW-SUPP-WI-IND",
    supplementalWageIndex="P-NEW-SUPP-WI")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixed_records(data, capacity):
    rows = data.splitlines()
    if not rows or len(rows) >= capacity or any(len(r) > 80 for r in rows):
        raise ValueError("Unsupported wage table size or record width")
    # Strip only line terminators and pad the declared fixed 80-byte FD.
    return b"".join(row.ljust(80, b" ") for row in rows)


def active(data):
    return [line[7:72].rstrip() for line in data.decode("cp1252").splitlines()
            if len(line) > 6 and line[6] not in "*/"]


def section(lines, first, last):
    start = next(i for i, line in enumerate(lines) if first in line)
    end = next(i for i in range(start + 1, len(lines)) if last in lines[i])
    return lines[start:end]


def output_fields(lines):
    stack, fields = [], []
    for line in lines:
        m = re.match(r"\s*(\d\d)\s+([\w-]+)(.*)", line)
        if not m or int(m[1]) == 88:
            continue
        level, name, tail = int(m[1]), m[2], m[3]
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, name))
        pic = re.search(r"\bPIC\s+([S9XV0-9()]+)", tail)
        if pic and name not in ("FILLER", "PPS-FILLER") and stack[0][1] in ("PPS-DATA", "PPS-ADDITIONAL-VARIABLES", "PPHOLDAR-HOLD-AREA"):
            fields.append({"id": "/".join(n for _, n in stack),
                           "reference": " OF ".join(n for _, n in reversed(stack)),
                           "numeric": "X" not in pic[1] and name != "PPS-CALC-VERS", "picture": pic[1]})
    if len({f['id'] for f in fields}) != len(fields) or len(fields) < 50:
        raise ValueError("Incomplete or duplicate output layout")
    for field in fields:
        if field['id'] == 'PPS-DATA/PPS-CALC-VERS':
            field['reference'] += '(1:5)'
            field['interpretation'] = 'raw version identifier; no numeric coercion'
    return fields


def literal(value):
    if isinstance(value, str):
        value = value.replace("-", "") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else value
        if not re.fullmatch(r"[A-Za-z0-9 ]*", value):
            raise ValueError("Unsupported generated input")
        return '"' + value + '"'
    return str(value)


def make_driver(source, claims, hold_copy, audit_sources):
    if len(claims) != 5:
        raise ValueError("Exactly five F0 cases required")
    lines = active(source)
    linkage = section(lines, "LINKAGE SECTION.", "PROCEDURE DIVISION")[1:]
    if linkage.count("COPY PPHOLDAR.") != 1:
        raise ValueError("Unexpected hold-area copy layout")
    # Expand only the public declaration in our generated free-format driver;
    # original source and copybook used to build CMS modules remain untouched.
    expanded = []
    for line in linkage:
        expanded.extend(active(hold_copy) if line == "COPY PPHOLDAR." else [line])
    linkage = expanded
    provider = section(lines, "01  PROV-NEW-HOLD.", "LINKAGE SECTION.")
    bill_size, bill_layout = layout(lines, 'BILL-DATA-2021')
    provider_size, provider_layout = layout(lines, 'PROV-NEW-HOLD')
    if provider_size != 310:
        raise ValueError('Provider layout width changed')
    aliases = {'P-NEW-CCR': 'P-NEW-OPER-CSTCHG-RATIO',
               'P-NEW-CMI-ADJ-CPD': 'P-NEW-FAC-SPEC-RATE',
               'P-NEW-HOSP-HRR-ADJUSTMT': 'P-HOSP-HRR-ADJUSTMT',
               'P-NEW-HOSP-READMISSION-REDU': 'P-HOSP-READMISSION-REDU',
               'P-NEW-VAL-BASED-PURCH-PARTIPNT': 'P-VAL-BASED-PURCH-PARTIPNT',
               'P-NEW-VAL-BASED-PURCH-ADJUST': 'P-VAL-BASED-PURCH-ADJUST'}
    for name, raw in audit_sources.items():
        size, other = layout(active(raw), 'PROV-NEW-HOLD')
        if size != provider_size:
            raise ValueError('Module provider layout width differs')
        for field in PROVIDER.values():
            target = aliases.get(field, field) if name == 'PPCAL215' else field
            if other[target] != provider_layout[field]:
                raise ValueError('Module provider input offset/type differs: ' + field)
    fields = output_fields(linkage)
    fields.append(dict(id="PRICER-OPT-VERS-SW/PPS-VERSIONS/PPDRV-VERSION",
                       reference="PPDRV-VERSION", numeric=False, picture="X(05)"))
    body = ["identification division.", "program-id. F0SMOKE.",
            "data division.", "working-storage section."] + linkage + provider
    body += ["01 F0-NUM PIC -(18)9.9(12).", "procedure division.",
             "if length of PROV-NEW-HOLD not = 310", "move 99 to return-code", "goback", "end-if"]
    for index, claim in enumerate(claims):
        if set(claim) != {"claimData", "providerData"} or set(claim['claimData']) != set(CLAIM) or set(claim['providerData']) != set(PROVIDER):
            raise ValueError("Unmapped generated input")
        body += ["initialize BILL-DATA-2021 PPS-DATA", "PRICER-OPT-VERS-SW PPS-ADDITIONAL-VARIABLES",
                 "PPHOLDAR-HOLD-AREA PROV-NEW-HOLD", 'move "P" to PRICER-OPTION-SW']
        for group, mapping in [('claimData', CLAIM), ('providerData', PROVIDER)]:
            body += [f"move {literal(value)} to {mapping[key]}" for key, value in claim[group].items()]
        body += ["move PROV-NEW-HOLD to PROV-RECORD-FROM-USER"]
        checks = []
        for group, mapping, record_layout, record_name in [
                ('claimData', CLAIM, bill_layout, 'BILL-DATA-2021'),
                ('providerData', PROVIDER, provider_layout, 'PROV-RECORD-FROM-USER')]:
            for key, value in claim[group].items():
                item = record_layout[mapping[key]]
                expected = encode_input(value, item)
                checks += [f'if {record_name}({item["offset"]+1}:{item["size"]}) not = "{expected}"',
                           'move 98 to return-code', 'goback', 'end-if']
        body += checks + [f'display "CASE|{index}"', 'display "INPUT|45"',
                 'call "PPOPN215" using BILL-DATA-2021 PPS-DATA',
                 "PRICER-OPT-VERS-SW PPS-ADDITIONAL-VARIABLES",
                 "PPHOLDAR-HOLD-AREA PROV-RECORD-FROM-USER",
                 "MSAX-TABLE-FROM-USER CBSA-TABLE-FROM-USER"]
        for i, field in enumerate(fields):
            if field['numeric']:
                body += ["move " + field['reference'] + " to F0-NUM",
                         f'display "FIELD|{i}|" function trim(F0-NUM)']
            else:
                body += [f'display "FIELD|{i}|" ' + field['reference']]
    body += ["move 0 to return-code", "goback."]
    return "\n".join(body) + "\n", fields


def encode_input(value, item):
    """Independent DISPLAY representation used to check the actual ABI bytes."""
    pic, width = item['picture'], item['size']
    if not pic or 'X' in pic:
        text = literal(value)[1:-1] if isinstance(value, str) else str(value)
        if len(text) > width:
            raise ValueError('Input text overflow')
        return text.ljust(width)
    parts = pic.split('V')
    scale = sum(int(n or 1) for n in re.findall(r'9(?:\((\d+)\))?', parts[1])) if len(parts) == 2 else 0
    number = Decimal(str(value)) * (10 ** scale)
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError('Input precision or sign mismatch')
    text = str(int(number))
    if len(text) > width:
        raise ValueError('Input numeric overflow')
    return text.zfill(width)


def normalize(value, numeric):
    if not numeric:
        return value.rstrip()
    n = Decimal(value.strip())
    if not n.is_finite():
        raise ValueError("Nonfinite output")
    return format(n.normalize(), 'f') if n else '0'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('work/cms/f0'))
    p.add_argument('--claims', type=Path, default=Path('docs/cms/generated-claims.json'))
    args = p.parse_args()
    root = args.root.resolve()
    raw = (root / PACKAGE).read_bytes()
    if sha(raw) != PIN:
        raise ValueError("Pinned CMS archive mismatch")
    with zipfile.ZipFile(root / PACKAGE) as archive:
        source = archive.read('PPOPN215')
        hold_copy = archive.read('PPHOLDAR')
        audit_sources = {n: archive.read(n) for n in ('PPDRV215', 'PPCAL215')}
        tables = {name: archive.read(name) for name in ('MSAX045', 'CBSA212')}
    src = root / PACKAGE.removesuffix('.zip')
    claims = json.loads(args.claims.read_text())
    driver, fields = make_driver(source, claims, hold_copy, audit_sources)
    path = root / 'F0SMOKE.cob'
    path.write_text(driver, encoding='utf-8')
    record = dict(notice='public CMS software, independently tested', source_modified=False,
                  module_layout_sha256={n: sha(v) for n,v in audit_sources.items()},
                  source_sha256=sha(source), hold_copy_sha256=sha(hold_copy), claims_sha256=sha(args.claims.read_bytes()),
                  driver_sha256=sha(path.read_bytes()), fields=fields, cases=[],
                  disclosure='Output bytes stay on runner; only canonical per-field SHA256 leaves runner. No comparison verdict published.')
    env = dict(os.environ, COB_LIBRARY_PATH=str(src))
    for name, dd, capacity in [('MSAX045', 'PPSMSAX', 9000), ('CBSA212', 'PPSCBSA', 8000)]:
        data = fixed_records(tables[name], capacity)
        target = root / (dd + '.fixed')
        target.write_bytes(data)
        env['DD_' + dd] = str(target)
        record.setdefault('table_adapters', {})[name] = dict(source_sha256=sha(tables[name]), fixed_sha256=sha(data), records=len(data)//80)
    exe = root / 'F0SMOKE'
    build = subprocess.run(['cobc', '-x', '-free', '-std=ibm', '-I', str(src), '-o', str(exe), str(path)], capture_output=True, timeout=90)
    record['build_returncode'] = build.returncode
    record['build_diagnostic_metadata'] = diagnostic_metadata(build.stderr.decode(errors='replace'), active(source))
    if build.returncode == 0:
        try:
            run = subprocess.run([str(exe)], cwd=root, env=env, capture_output=True, timeout=60)
            record.update(run_returncode=run.returncode, stdout_sha256=sha(run.stdout), stderr_sha256=sha(run.stderr))
            # No raw payment output, even on parse/error paths.
            for line in run.stdout.decode('ascii').splitlines():
                if line.startswith('CASE|'):
                    index = int(line.split('|')[1]); assert index == len(record['cases'])
                    record['cases'].append({'index': index, 'fields': {}, 'input_checks': 0})
                elif line == 'INPUT|45':
                    record['cases'][-1]['input_checks'] += 45
                elif line.startswith('FIELD|'):
                    _, index, value = line.split('|', 2); field = fields[int(index)]
                    canonical = normalize(value, field['numeric'])
                    values = record['cases'][-1]['fields']; assert field['id'] not in values
                    values[field['id']] = sha(canonical.encode())
                else:
                    raise ValueError('Unexpected output; raw bytes withheld')
            record['complete'] = run.returncode == 0 and len(record['cases']) == 5 and all(len(c['fields']) == len(fields) and c['input_checks'] == 45 for c in record['cases'])
        except (subprocess.TimeoutExpired, ValueError, InvalidOperation, AssertionError, UnicodeError, IndexError):
            record['complete'] = False
            record['failure'] = 'Runtime/format boundary; raw bytes withheld'
    else:
        record['complete'] = False
    (root / 'smoke-hashes.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    require_smoke(record)


if __name__ == '__main__':
    main()
