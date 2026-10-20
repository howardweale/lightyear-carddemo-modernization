"""Account scope/date projection; evidence verification must precede publication."""
from datetime import date
import re
from tools.carddemo_account_proof import GROUPS

ENGINE_PROGRAMS = ('COACTVWC', 'COACTUPC', 'COPAUS0C', 'COPAUS1C')


def _strings(value, reason):
    if (not isinstance(value, list) or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(set(value)) != len(value)):
        raise ValueError(reason)
    return list(value)


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('account-publication-date')
    return date.fromisoformat(value)


def project_scope(group, scopes, source, measurement_date):
    """Project already hash-bound scopes; never infer whole-screen retirement."""
    if (group.get('program') != 'COACTUPC' or group.get('whole_screen_idiomatic') is not False
        or set(scopes) != set(GROUPS)):
        raise ValueError('account-publication-scope')
    if _date(group['publication_date']) < _date(measurement_date):
        raise ValueError('account-publication-before-measurement')
    if (not isinstance(source, dict) or set(source) != {'path', 'sha256'}
        or source['path'] != 'spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl'
        or not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256'])):
        raise ValueError('account-publication-source')
    result = {}; seen = set()
    for key in GROUPS:
        scope = scopes[key]
        if (scope.get('schema') != 'carddemo-idiomatic-java-scope/1'
            or scope.get('program') != 'COACTUPC' or scope.get('source') != source
            or scope.get('remaining_statement_engine_programs') != list(ENGINE_PROGRAMS)):
            raise ValueError('account-publication-scope-source')
        paragraphs = _strings(scope.get('validation_paragraphs'), 'account-publication-paragraphs')
        if any(not re.fullmatch(r'[0-9]{4}-[A-Z0-9-]+', item) for item in paragraphs) or seen.intersection(paragraphs):
            raise ValueError('account-publication-paragraphs')
        seen.update(paragraphs)
        result[key] = dict(validation_paragraphs=paragraphs,
            rule_methods=_strings(scope.get('rule_methods'), 'account-publication-methods'),
            java_files=_strings(scope.get('java_files'), 'account-publication-java-files'))
    return dict(program='COACTUPC', publication_date=group['publication_date'],
        measurement_date=measurement_date, whole_screen_idiomatic=False, groups=result,
        validation_paragraph_count=len(seen), remaining_statement_engine_programs=list(ENGINE_PROGRAMS))


def scope_paragraph(value):
    return (f"As of {value['publication_date']}, the COACTUPC publication scope covers "
        f"{value['validation_paragraph_count']} validation paragraphs in {len(value['groups'])} groups. "
        f"The bound proof retains its measurement date {value['measurement_date']}. "
        'The whole account screen remains incomplete. Statement-engine programs: '
        + ', '.join(value['remaining_statement_engine_programs']) + '. '
        'Scope classification alone does not establish a passing proof or merge readiness.')
