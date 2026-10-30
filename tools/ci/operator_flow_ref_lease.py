"""Exact E-to-M branch lease arguments, never a sender or approval.

GitHub REST ref updates have no expected-old-SHA parameter. The eventual
reviewed host transport must use this explicit Git lease and sole-parent M,
with one exact refspec, fixed repository, isolated Git configuration, original
environment filtering, live host guards, exclusive intent and final readback.
No API, subprocess, credential, signature, nonce or filesystem operation here.
"""
import re
from tools.ci.operator_flow_metadata import MESSAGE,object_id,require

def exact_ref_lease(candidate,*,executable,metadata_head,branch_ref):
    require(all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (executable,metadata_head))
        and executable!=metadata_head,'ref-lease-exact-E-M')
    require(type(branch_ref) is str and re.fullmatch('refs/heads/codex/[A-Za-z0-9_-]+',branch_ref),
        'ref-lease-exact-codex-branch')
    require(type(candidate) is dict and candidate.get('parent')==executable
        and candidate.get('commit')==metadata_head
        and all(candidate.get(k) is False for k in ('native_proof_verified','full_guards_passed',
            'publish_ready','publication_authorized','full_route_passed','real_pack_ready')),
        'ref-lease-candidate-no-authority')
    epoch=candidate.get('commit_epoch');tree=candidate.get('tree')
    require(type(epoch) is int and 1<=epoch<10**11 and type(tree) is str
        and re.fullmatch('[0-9a-f]{40}',tree),'ref-lease-original-commit-fields')
    identity='Codex <codex@openai.com> '+str(epoch)+' +0000'
    raw=('tree '+tree+'\nparent '+executable+'\nauthor '+identity+
        '\ncommitter '+identity+'\n\n'+MESSAGE).encode()
    require(type(candidate.get('objects')) is dict
        and candidate['objects'].get(metadata_head)==('commit',raw)
        and object_id('commit',raw)==metadata_head,'ref-lease-original-sole-parent-bytes')
    # The lease option can otherwise allow non-fast-forward updates. Requiring
    # exact raw M with sole parent E above restricts this to one fast-forward.
    # Never use tracking refs, an empty expect, '+' or a general --force option.
    return ('--porcelain','--no-follow-tags','--recurse-submodules=no','--signed=false',
        '--force-with-lease='+branch_ref+':'+executable,metadata_head+':'+branch_ref)
