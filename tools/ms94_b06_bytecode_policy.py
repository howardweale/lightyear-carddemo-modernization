"""Prospective B06 JVM admission; never relax compiled-byte identity checks."""
from tools.ms94_b06_admission import check

POLICY = 'untransformed-classes-jdwp-only-v1'
JDWP = '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=*:5005'


def validate_policy(spec):
    check(spec.get('bytecode_policy') == POLICY, 'observer-bytecode-policy-missing')


def validate_jvm(owner, spec):
    """Check the host-read suspended process, before any JDI attach/resume.

    The same check is required on the signed receipt during offline replay.
    A Maven skip flag alone is not proof that an agent was absent.
    """
    validate_policy(spec)
    check(owner.get('java_binary_sha256') == spec['java_binary_sha256'], 'observer-java-changed')
    args = owner.get('arguments')
    check(isinstance(args, list) and args and all(isinstance(a, str) for a in args),
          'observer-jvm-arguments-missing')
    check(args.count(JDWP) == 1, 'observer-not-suspended-at-start')
    agents = [a for a in args if a.startswith(('-javaagent', '-agentlib', '-agentpath', '-Xrun'))]
    check(agents == [JDWP], 'observer-unapproved-bytecode-agent')
    check(not any(a.startswith('@') for a in args), 'observer-unexpanded-jvm-arguments')
    check(owner.get('jvm_option_environment_present') == [], 'observer-jvm-option-environment')
    if 'expected_jvm_arguments' in spec:
        check(args == spec['expected_jvm_arguments'], 'observer-built-command-differs')
    return True
