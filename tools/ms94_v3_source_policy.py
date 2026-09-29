"""Public posting restriction, checked before the private business judge.

This is a bounded source policy, not a Java sandbox or proof against malicious
programs. Isolation, owned-row checks and native history bounds remain required.
"""
import re
from lightyear_calibration.ms94_v3_errors import business_require

FORBIDDEN = frozenset(('postDocument', 'postImmediate', 'getDocument',
    'forName', 'getDeclaredMethod', 'getDeclaredMethods', 'getMethod', 'getMethods',
    'invoke', 'MethodHandles', 'setAccessible', 'repost', 'rePost'))


def check(source):
    # Java processes Unicode escapes before comments and string literals.
    source = re.sub(r'\\u+([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), source)
    masked = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: '\n' * m[0].count('\n') + ' ', source)
    violations = [{'identifier':m[0], 'line':masked[:m.start()].count('\n')+1}
                  for m in re.finditer(r'[A-Za-z_$][\w$]*', masked) if m[0] in FORBIDDEN]
    business_require(not violations, 'Candidate bypasses the public posting API')
    return {'passed':True, 'policy':'sdk-only-explicit-posting-v1',
            'limit':'Static restriction; no general adversarial-Java safety claim.'}
