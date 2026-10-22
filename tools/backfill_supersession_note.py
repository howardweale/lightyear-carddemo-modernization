"""Render the dated explanation without changing import decisions or history."""

def render(record):
    lines=['# Backfill supersession clarification', '', 'As of '+record['recorded_on']+'. '+record['scope'], '']
    for row in record['records']:
        lines += ['## '+row['path'].rsplit('/',1)[-1], '',
            str(row['historical_record_count'])+' historical records; '+str(row['source_commit_count'])+' source commit(s).', '',
            row['reason'], '']
    lines += ['The retired contract identities remain refused. This note creates no signature, activation or execution authority.', '']
    return '\n'.join(lines)
