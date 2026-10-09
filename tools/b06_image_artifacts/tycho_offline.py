"""Read-only diagnosis of preserved failed closure outputs. Never invent evidence."""
import hashlib,json
from pathlib import Path
from .tycho_runtime import layout,one_properties_file,read


def inspect(attempt):
    attempt=Path(attempt);root=attempt/'results'
    observation=(root/'closure-observation.json').read_bytes();obs=json.loads(observation)
    configurations=list((root/'runtime').rglob('config.ini'))
    if len(configurations)!=1:raise ValueError('exactly-one-preserved-config-required')
    config=configurations[0].read_bytes()
    measured=(root/'measured-command.json').read_bytes();maven=(root/'command.json').read_bytes()
    log=(root/'maven.log').read_bytes()
    lines=[s.strip() for s in log.decode('utf-8').splitlines()
           if s.strip().startswith('['+obs['java_home']+'/bin/java,') and '-testproperties' in s]
    if len(lines)!=1 or not lines[0].endswith(']'):raise ValueError('unambiguous-preserved-tycho-fork-log-required')
    # The log is corroboration only; never promoted to a signed /2 observation.
    command=lines[0][1:-1].split(', ')
    parsed=layout(config,obs,command)
    missing=[]
    try: properties=one_properties_file(root/'runtime').read_bytes()
    except ValueError: properties=None;missing.append('target/surefire.properties was not preserved')
    if obs.get('schema')!='b06-runtime-launch-observation/2':missing.append('new observed fork argv and bundle symbolic identities absent from historical /1 observation')
    if not (root/'measured-inventory.json').exists():missing.append('measured runtime inventory was never produced')
    if not (attempt/'runtime-launch-receipt.json').exists():missing.append('no successful signed runtime-launch receipt exists')
    if properties is not None and obs.get('schema')=='b06-runtime-launch-observation/2':read(config,properties,obs,obs['fork_command'])
    digest=lambda raw:hashlib.sha256(raw).hexdigest()
    return dict(schema='b06-tycho-preserved-review/1',native_admission=False,
        full_producer_replay_passed=False,producer_replay_blocked_by=missing,
        layout_checks_passed=True,configured_bundle_entries=len(parsed['equinox_bundles']),
        observed_non_system_bundles=len(parsed['observed_bundle_paths']),
        duplicate_config_bundle_paths=parsed['duplicate_config_bundle_paths'],
        boot_classpath=parsed['boot_classpath'],surefire_properties_preserved=properties is not None,
        fork_command_source='preserved Maven log; diagnostic corroboration only',
        input_sha256={'observation':digest(observation),'config.ini':digest(config),
                      'measured-command.json':digest(measured),'command.json':digest(maven),'maven.log':digest(log)},
        model_calls=0,docker_commands=0,review='operator review; not independent attestation')
