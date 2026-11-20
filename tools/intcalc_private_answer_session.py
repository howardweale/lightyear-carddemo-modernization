"""Howard-launched H2b private answer operation; no agent/CI execution."""
import argparse
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
import warnings

from tools import intcalc_private_reference_host as hostlib
from tools import intcalc_heldout_encrypted_stream as stream
from tools import intcalc_reference_execution as ref

CODES=frozenset(('answer-arguments','answer-authority','answer-clock','answer-custody',
    'answer-host-qualification','answer-policy','answer-source','answer-encryptor',
    'answer-seed','answer-operator','answer-container','answer-stream','answer-worker',
    'answer-cleanup','answer-postflight','answer-fault'))


def require(ok,code):
    if not ok:raise stream.Refused(code)


def refusal(error):
    if isinstance(error,stream.Refused) and len(error.args)==1 and error.args[0] in CODES|stream.CODES:
        return error.args[0]
    return 'answer-fault'


def policy(row):
    stream.closed(row,('schema','count','source_hashes','worker_sha256','generator_sources',
        'reference_binding','package_library_sha256','age','recipient','recipient_sha256',
        'recipient_designation_sha256','host_canary_sha256','licence_review_sha256'))
    require(row['schema']=='heldout-answer-policy/1' and type(row['count']) is int and 1<=row['count']<=64,'answer-policy')
    for k in ('worker_sha256','package_library_sha256','recipient_sha256','recipient_designation_sha256',
              'host_canary_sha256','licence_review_sha256'):stream.digest(row[k])
    stream.closed(row['age'],('path','sha256','version'));stream.digest(row['age']['sha256'])
    require(type(row['age']['version']) is str and bool(row['age']['version']), 'answer-encryptor')
    stream.closed(row['reference_binding'],('path','sha256'));stream.digest(row['reference_binding']['sha256'])
    require(type(row['source_hashes']) is dict and len(row['source_hashes'])>=7,'answer-source')
    for path,digest in row['source_hashes'].items():
        require(type(path) is str and not Path(path).is_absolute() and '..' not in Path(path).parts,'answer-source')
        stream.digest(digest)
    require(row['package_library_sha256']==hostlib.PACKAGE,'answer-policy')
    require(type(row['recipient']) is str and re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',row['recipient'])
        and stream.sha(row['recipient'].encode('ascii'))==row['recipient_sha256'],'answer-encryptor')


def canary_receipt(raw,pol):
    require(stream.sha(raw)==pol['host_canary_sha256'],'answer-encryptor')
    row=hostlib.strict(raw)
    stream.closed(row,('schema','operator','encryptor_sha256','recipient_sha256',
        'public_canary_only','roundtrip_match','interruption_refused','exclusive_write',
        'file_directory_sync_readback','usb_identity_only','raw_private_values_included'))
    require(row['schema']=='heldout-age-host-canary/1' and row['operator']=='Howard'
        and row['encryptor_sha256']==pol['age']['sha256'] and row['recipient_sha256']==pol['recipient_sha256']
        and all(row[k] is True for k in ('public_canary_only','roundtrip_match','interruption_refused',
            'exclusive_write','file_directory_sync_readback','usb_identity_only'))
        and row['raw_private_values_included'] is False,'answer-encryptor')


def admit(authority,raw,expected,p,pol,custody_raw,qualification_raw,now):
    stream.closed(authority,('schema','authority','operation_id','mode','source_commit','source_tree',
        'profile_sha256','policy_sha256','custody_sha256','qualification_sha256','valid_from','expires_at'))
    require(stream.sha(raw)==expected and authority['schema']=='heldout-private-answer-approval/1'
        and authority['authority']=='Howard' and authority['mode']=='GENERATE_ENCRYPT_COMMIT','answer-authority')
    stream.digest(authority['operation_id'])
    require(authority['source_commit']==p['source_commit'] and authority['source_tree']==p['source_tree']
        and authority['profile_sha256']==stream.sha(stream.canonical(p))
        and authority['policy_sha256']==stream.sha(stream.canonical(pol))
        and authority['custody_sha256']==stream.sha(custody_raw)
        and authority['qualification_sha256']==stream.sha(qualification_raw),'answer-authority')
    start,end=hostlib.aware(authority['valid_from']),hostlib.aware(authority['expires_at'])
    require(start<=now<end and 0<(end-start).total_seconds()<=7200,'answer-clock')
    q=hostlib.strict(qualification_raw)
    require(q.get('schema')=='ha-public-host-qualification/1' and q.get('status')=='CRITERION_MET'
        and q.get('source_commit')==p['source_commit'] and q.get('source_tree')==p['source_tree']
        and q.get('profile_sha256')==authority['profile_sha256'] and q.get('comparison_criterion_met') is True
        and q.get('cases')==16 and q.get('probes')==9 and q.get('cleanup') is True
        and q.get('package_library_sha256')==hostlib.PACKAGE and q.get('public_suite_sha256')==hostlib.SUITE
        and q.get('reviewed_qualification_sha256')==hostlib.QUALIFICATION_RECEIPT,'answer-host-qualification')
    c=hostlib.strict(custody_raw)
    hostlib.custody(c,authority['operation_id'],authority['profile_sha256'],p['source_commit'],p['source_tree'])
    require(c['public_host_qualification']=='PASSED' and c['qualification_receipt_sha256']==authority['qualification_sha256']
        and start<=hostlib.aware(c['observed_at_with_offset'])<=now,'answer-custody')
    return min(5400,(end-now).total_seconds())


def boundary(row,image,root,permit,uid):
    c,h=row['Config'],row['HostConfig']
    require(c['Image']==image and c['User']==uid and c['OpenStdin'] is True and c['Tty'] is False
        and h['NetworkMode']=='none' and h['ReadonlyRootfs'] is True and h['CapDrop']==['ALL']
        and h['Memory']==2147483648 and h['PidsLimit']==128 and h['NanoCpus']==2000000000
        and h['LogConfig']['Type']=='none' and h['CgroupnsMode']=='private'
        and not h.get('Privileged') and not h.get('Devices') and not h.get('Binds')
        and any(x.split(':')[0]=='no-new-privileges' for x in h['SecurityOpt']),'answer-container')
    mounts={m['Destination']:m for m in row['Mounts'] if m['Type']!='tmpfs'}
    require(set(mounts)=={'/source','/answer-policy.json'},'answer-container')
    for dest,src in (('/source',str(root)),('/answer-policy.json',str(permit))):
        require(mounts[dest]['Type']=='bind' and mounts[dest]['Source']==src and mounts[dest]['RW'] is False,'answer-container')
    require(set(h['Tmpfs'])=={'/tmp','/work'},'answer-container')


class Reader:
    def __init__(self,child,deadline,wall):
        self.child,self.deadline,self.wall=child,deadline,wall
        os.set_blocking(child.stdout.fileno(),False)
        self.selector=selectors.DefaultSelector();self.selector.register(child.stdout,selectors.EVENT_READ)
    def take(self,n):
        raw=bytearray()
        while len(raw)<n:
            require(time.monotonic()<self.deadline and time.time()<self.wall,'answer-clock')
            if not self.selector.select(min(.25,self.deadline-time.monotonic())):continue
            try:part=os.read(self.child.stdout.fileno(),min(n-len(raw),65536))
            except BlockingIOError:continue
            require(bool(part),'answer-stream');raw.extend(part)
        return bytes(raw)
    def row(self):
        size=int.from_bytes(self.take(8),'big');require(0<size<=stream.CASE_CAP,'answer-stream')
        return hostlib.strict(self.take(size))
    def end(self,count):
        row=self.row();stream.closed(row,('schema','count','complete'))
        require(row==dict(schema='heldout-answer-end/1',count=count,complete=True),'answer-stream')
        while True:
            require(time.monotonic()<self.deadline and time.time()<self.wall,'answer-clock')
            if not self.selector.select(.1):continue
            try:extra=os.read(self.child.stdout.fileno(),1)
            except BlockingIOError:continue
            require(extra==b'','answer-stream');break
        require(self.child.wait(timeout=max(.001,self.deadline-time.monotonic()))==0,'answer-worker')
        return True
    def close(self):self.selector.close();self.child.stdout.close()


def build_image(host,p,run,deadline):
    binding,_,_,_,_=hostlib.public_bindings()
    context=run/'build-context';(context/'tools/legacy_twin').mkdir(parents=True,mode=0o700)
    config=run/'build-config';config.mkdir(mode=0o700)
    for key in ('recipe','installer'):
        hostlib.exclusive(context/binding[key]['path'],ref.joined(ref.ROOT,binding[key]))
    iid=run/'image.id'
    host.commands.out(['docker','--config',str(config),'--host','unix:///var/run/docker.sock',
        'build','--platform','linux/amd64','--file',str(context/binding['recipe']['path']),
        '--iidfile',str(iid),str(context)],seconds=min(1800,deadline-time.monotonic()),cap=16777216)
    image=hostlib.read(iid).decode().strip()
    require(re.fullmatch('sha256:[a-f0-9]{64}',image),'answer-container')
    row=hostlib.strict(host.docker('image','inspect',image))
    require(len(row)==1 and row[0]['Id']==image and row[0]['Architecture']=='amd64' and row[0]['Os']=='linux','answer-container')
    return image


def operation(host,p,pol,authority,approval_hash,deadline,wall,seed_prompt,postflight):
    root=hostlib.private_directory(p['private_root'])
    run=root/('answers-'+authority['operation_id']);run.mkdir(mode=0o700)
    permit=run/'policy.json';hostlib.exclusive(permit,stream.canonical(pol))
    image=build_image(host,p,run,deadline)
    # Recheck public executable pins before asking for any private input.
    stream.pin_executable(pol['age']['path'],pol['age']['sha256'])
    docker_path=p['binaries']['docker']['path']
    require(stream.sha(hostlib.read(docker_path,268435456))==p['binaries']['docker']['sha256'],'answer-source')
    seed_text=seed_prompt()
    require(type(seed_text) is str and re.fullmatch('[0-9a-fA-F]{64}',seed_text),'answer-seed')
    seed=bytes.fromhex(seed_text);del seed_text
    name='ha-answer-'+authority['operation_id'][:32];uid=str(os.getuid())+':'+str(os.getgid())
    made=False;child=None;reader=None;cleaned=False
    def cleanup():
        nonlocal cleaned
        if child is not None and child.poll() is None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait(timeout=5)
        if made:
            host.docker('rm','-f',name,seconds=20)
            require(not host.docker('ps','-a','--filter','name=^/'+name+'$','--format','{{.Names}}').strip(),'answer-cleanup')
        cleaned=True
    try:
        # Register even before create returns: a timed-out create may have succeeded.
        made=True
        host.docker('create','--name',name,'--interactive','--platform=linux/amd64','--network=none',
            '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--memory=2g','--cpus=2',
            '--pids-limit=128','--log-driver=none','--cgroupns=private','--user',uid,
            '--tmpfs','/tmp:rw,nosuid,nodev,size=256m,mode=1777',
            '--tmpfs','/work:rw,nosuid,nodev,exec,size=1g,mode=1777',
            '--mount','type=bind,src='+str(ref.ROOT.resolve())+',dst=/source,readonly',
            '--mount','type=bind,src='+str(permit)+',dst=/answer-policy.json,readonly',
            '--env','PYTHONPATH=/source/src:/source','--env','PYTHONDONTWRITEBYTECODE=1',
            '--workdir','/source',image,'python3','-B','tools/intcalc_private_answer_worker.py')
        boundary(hostlib.strict(host.docker('inspect',name))[0],image,ref.ROOT.resolve(),permit,uid)
        child=subprocess.Popen([docker_path,'--config',p['client_config'],'--host','unix:///var/run/docker.sock',
            'start','--attach','--interactive',name],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env={},close_fds=True,start_new_session=True)
        # Exactly32bytes fit in an empty pipe; no seed argv/env/file/log.
        child.stdin.write(seed);child.stdin.close();del seed
        reader=Reader(child,deadline-90,wall)
        first=reader.row();stream.closed(first,('schema','sha256','count'))
        require(first['schema']=='heldout-input-commitment/1' and first['count']==pol['count'],'answer-stream')
        stream.digest(first['sha256'])
        binding=dict(source_commit=p['source_commit'],source_tree=p['source_tree'],
            generator_sha256=pol['generator_sources']['generator_sha256'],
            reference_sha256=pol['reference_binding']['sha256'],profile_sha256=authority['profile_sha256'],
            host_qualification_sha256=authority['qualification_sha256'],input_commitment_sha256=first['sha256'],
            recipient_sha256=pol['recipient_sha256'],encryptor_sha256=pol['age']['sha256'],
            policy_sha256=authority['policy_sha256'],authority_sha256=approval_hash)
        def rows():
            for _ in range(pol['count']):yield reader.row()
        def done():
            reader.end(pol['count']);cleanup()
            hostlib.source_identity(host.commands,p);host.observe()
            return True
        store=stream.PrivateStore(root,'encrypted-'+authority['operation_id'])
        make=lambda fd,end:stream.AgeSink(pol['age']['path'],pol['age']['sha256'],pol['recipient'],pol['recipient_sha256'],fd,end)
        return stream.write_answers(rows(),pol['count'],binding,store,make,done,postflight,deadline)
    finally:
        if reader is not None:reader.close()
        if not cleaned:cleanup()


class Parser(argparse.ArgumentParser):
    def error(self,message):raise stream.Refused('answer-arguments')


def main(argv=None):
    parser=Parser()
    for key in ('profile','policy','custody','qualification','approval','postflight','canary'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--approval-sha256',required=True)
    try:
        a=parser.parse_args(argv)
        require(os.name=='posix' and not os.environ.get('GITHUB_ACTIONS') and sys.stdin.isatty() and sys.stdout.isatty(),'answer-operator')
        os.umask(0o077);data={}
        for key in ('profile','policy','custody','qualification','approval','canary'):
            path=getattr(a,key);hostlib.private_control_file(path);data[key]=hostlib.read(path)
        p=hostlib.strict(data['profile']);hostlib.profile(p)
        pol=hostlib.strict(data['policy']);policy(pol);canary_receipt(data['canary'],pol)
        authority=hostlib.strict(data['approval'])
        seconds=admit(authority,data['approval'],a.approval_sha256,p,pol,data['custody'],data['qualification'],datetime.now(timezone.utc))
        require(input('Type reviewed approval SHA256: ').strip()==a.approval_sha256,'answer-authority')
        seconds=admit(authority,data['approval'],a.approval_sha256,p,pol,data['custody'],data['qualification'],datetime.now(timezone.utc))
        deadline=time.monotonic()+seconds;wall=hostlib.aware(authority['expires_at']).timestamp()
        commands=hostlib.Commands(p['binaries'],deadline,wall)
        hostlib.source_identity(commands,p);host=hostlib.Host(p,commands);host.observe()
        require(not a.postflight.exists(),'answer-postflight')
        def seed_prompt():
            with warnings.catch_warnings():
                warnings.simplefilter('error',getpass.GetPassWarning)
                return getpass.getpass('Private seed (64 hex characters): ')
        def postflight():
            began=datetime.now(timezone.utc)
            expected=input('Perform custody postflight; type receipt SHA256: ').strip()
            hostlib.private_control_file(a.postflight);raw=hostlib.read(a.postflight)
            require(stream.sha(raw)==expected,'answer-postflight');post=hostlib.strict(raw)
            hostlib.custody(post,authority['operation_id'],authority['profile_sha256'],p['source_commit'],p['source_tree'],post=True)
            require(began<=hostlib.aware(post['observed_at_with_offset'])<=datetime.now(timezone.utc)
                and time.time()<wall,'answer-postflight')
            return expected
        result=operation(host,p,pol,authority,a.approval_sha256,deadline,wall,seed_prompt,postflight)
        print(stream.canonical(result).decode('ascii'));return 0
    except BaseException as error:
        print(refusal(error),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
