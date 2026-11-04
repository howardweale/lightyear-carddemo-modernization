"""Fixed publisher Git command/environment and local config checks.

No subprocess or write entry. The actual host caller must own the original
candidate, exact operation approval, exclusive intent, current native/full host
guards and original process result. Do not execute this command in scratch CI.
"""
import hashlib,os
from pathlib import Path
from lightyear_execution.tower_drill_reservation import _github_subprocess_environment
from tools.ci.operator_flow_metadata import require
from tools.ci.operator_flow_ref_lease import exact_ref_lease

REMOTE='https://github.com/howardweale/lightyear-carddemo-modernization.git'

def publisher_git_environment():
    # Preserve the original exclusion-before-value-read helper. Never capture
    # credentials or change the caller's environment. Drop every Git override,
    # debug trace and interactive helper; ordinary GitHub auth stays in child.
    original=_github_subprocess_environment()
    blocked={'factory_candidate_signing_key','ssh_askpass','gh_debug'}
    env={k:v for k,v in original.items() if not k.upper().startswith('GIT_') and k.casefold() not in blocked}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never',GH_PROMPT_DISABLED='1',GH_HOST='github.com',
        LC_ALL='C',LANG='C')
    return env

def check_local_transport_config(raw,executable_root):
    """Parse Git --local --no-includes --null --list output, not config text.

    Original host caller must collect it with the isolated environment and
    compare stable config bytes before/after. Unknown keys refuse. No include,
    credential, hook, filter, URL rewrite, push default or remote-group allowed.
    """
    require(type(raw) is bytes and 0<len(raw)<=65536 and raw.endswith(b'\0'),'transport-config-size')
    try:rows=raw[:-1].decode('utf-8').split('\0')
    except UnicodeError:raise ValueError('transport-config-encoding') from None
    config={}
    for row in rows:
        require('\n' in row,'transport-config-record');key,value=row.split('\n',1)
        require(key==key.lower() and key not in config and '\n' not in value and '\r' not in value,
            'transport-config-duplicate-or-framing')
        config[key]=value
    allowed={'core.repositoryformatversion':{'0'},'core.filemode':{'true','false'},
        'core.bare':{'false'},'core.logallrefupdates':{'true'},'core.autocrlf':{'false'},
        'core.ignorecase':{'true','false'},'core.symlinks':{'true','false'},
        'core.precomposeunicode':{'true','false'}}
    root=Path(executable_root)
    require(root.is_absolute(),'transport-config-independent-E-path')
    origin={'remote.origin.url':{str(root),root.as_posix()},
        'remote.origin.fetch':{'+refs/heads/*:refs/remotes/origin/*'}}
    allowed.update(origin)
    require(all(key in allowed and value in allowed[key] for key,value in config.items()),
        'transport-config-unapproved-entry')
    require(config.get('core.repositoryformatversion')=='0' and config.get('core.bare')=='false'
        and config.get('core.autocrlf')=='false','transport-config-required-core')
    require(not set(origin).intersection(config) or set(origin)<=set(config),'transport-config-origin-pair')
    return hashlib.sha256(raw).hexdigest()

def checked_push_command(candidate,*,executable,metadata_head,branch_ref,metadata_root,empty_hooks):
    # Filesystem isolation, stable source/config checks and empty hooks directory
    # are owned by the host caller; this only fixes command structure and scope.
    root=Path(metadata_root);hooks=Path(empty_hooks)
    require(root.is_absolute() and hooks.is_absolute() and root!=hooks
        and not hooks.is_relative_to(root) and not root.is_relative_to(hooks),'transport-independent-paths')
    args=exact_ref_lease(candidate,executable=executable,metadata_head=metadata_head,branch_ref=branch_ref)
    return ('git','--no-optional-locks','-c','core.hooksPath='+str(hooks),
        '-c','credential.helper=','-c','credential.helper=!gh auth git-credential',
        '-c','credential.interactive=false','-c','core.abbrev=40',
        '-c','push.followTags=false','-c','push.recurseSubmodules=no','-c','push.gpgSign=false',
        '-C',str(root),'push',*args[:-1],REMOTE,args[-1])
