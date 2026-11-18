"""Public-only fresh-exec Docker worker. No provider, oracle or hidden port."""
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time
import uuid

from lightyear_factory import public_repair_controller as c
from lightyear_factory.public_repair_durable import full_sync, open_parent, close_quiet

JDK = '8def71d61fd7f95b08480f51e8ac35e37ec87a0aaad6950a6f1e35c771de5b2d'
JRE = '3d25d5cb6ca22137a17d2aeddc7b965027ce1e404d52c5c92a8796cece4d7b07'
JAVAC = '1c6a574beed14cd3c5a48218359fbdb2c6be775ef777cf8338f080213187c0dc'
JAR = '1998d56064b12968a9dd4f62bf787a3e30c9fc8a46614437361e18bed45cc444'
DATA = 8*1024*1024
JAR_BYTES = 16*1024*1024
INPUTS = ('ACCTFILE','TCATBALF','DISCGRP','XREFFILE')
OUTPUTS = ('ACCTFILE','TRANSACT')
COMMON = ['--pull=never','--platform=linux/arm64','--network=none','--read-only',
    '--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=64',
    '--memory=512m','--cpus=1','--user=65534:65534','--log-driver=none']
_IN_WORKER = False
CODES = frozenset(('worker-posix','worker-path','worker-file','worker-size','worker-readback',
    'worker-write','worker-deadline','worker-command-limit','worker-reap','worker-boundary',
    'worker-archive-cap','worker-archive','worker-output-contract','worker-docker-config',
    'worker-docker','worker-resource','worker-platform','worker-image','worker-copy',
    'worker-remove','worker-absence','worker-source','worker-helper','worker-build-infrastructure',
    'worker-tools','worker-javac-fault','worker-jar','worker-artifact','worker-input','worker-clock',
    'worker-stop','worker-runtime-infrastructure','worker-request','worker-prefix','worker-cli',
    'worker-admission','worker-endpoint','worker-child','worker-build-order','worker-build-join',
    'worker-limits','worker-case-order','worker-arguments','worker-fault'))


class Refused(ValueError):
    pass


def require(ok,code):
    if not ok:raise Refused(code)


class LimitsRefused(Refused):
    """Exact integer time units preserve sub-nanosecond threshold differences."""
    def __init__(self, failed, limits, deadline, now):
        super().__init__('worker-limits')
        def finite(value):
            return type(value) is int or type(value) is float and math.isfinite(value)

        def delta(left, right):
            if not (finite(left) and finite(right)):
                return None
            value = left - right
            return value if finite(value) else None

        execution = limits.get('execution_deadline') if isinstance(limits, dict) else None
        cleanup = limits.get('cleanup_deadline') if isinstance(limits, dict) else None
        output = limits.get('output_bytes') if isinstance(limits, dict) else None
        times = dict(execution_remaining_ticks=delta(execution, now),
                     cleanup_gap_ticks=delta(cleanup, execution),
                     cleanup_minus_outer_ticks=delta(cleanup, deadline))
        ratios = {k: v.as_integer_ratio() for k, v in times.items() if v is not None}
        units = max((d for _, d in ratios.values()), default=1)
        ticks = {k: None for k in times}
        for k, (n, d) in ratios.items():
            ticks[k] = n * (units // d)
        byte_ratio = output.as_integer_ratio() if finite(output) else (None, None)
        self.evidence = dict(schema='public-worker-limits-refusal/1', code='worker-limits',
                             failed=failed, ticks_per_second=units,
                             output_bytes=byte_ratio[0] if byte_ratio[1] == 1 else None,
                             output_bytes_numerator=byte_ratio[0], output_bytes_denominator=byte_ratio[1], **ticks)


def check_public_limits(limits, deadline):
    failed = None
    if set(limits) != {'execution_deadline', 'cleanup_deadline', 'output_bytes'}:
        failed = 'keys'
    elif limits['output_bytes'] != DATA:
        failed = 'output-bytes'
    elif not limits['cleanup_deadline'] <= deadline:
        failed = 'cleanup-after-outer'
    elif not 0 < limits['cleanup_deadline'] - limits['execution_deadline']:
        failed = 'cleanup-gap-lower'
    elif not limits['cleanup_deadline'] - limits['execution_deadline'] <= 5:
        failed = 'cleanup-gap-upper'
    now = time.monotonic()
    if failed is None:
        remaining = limits['execution_deadline'] - now
        if not 0 < remaining:
            failed = 'execution-remaining-lower'
        elif not remaining <= 15:
            failed = 'execution-remaining-upper'
    if failed is not None:
        raise LimitsRefused(failed, limits, deadline, now)


def safe(path, *, directory=False):
    require(os.name=='posix','worker-posix')
    path=Path(path)
    require(path.is_absolute() and path==path.resolve(strict=True),'worker-path')
    for item in (path,*path.parents):
        require(not item.is_symlink(),'worker-path')
    info=path.stat()
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),'worker-file')
    return path


def read(path,cap):
    path=safe(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size<=cap,'worker-size')
        chunks=[];left=cap+1
        while left:
            block=os.read(fd,min(65536,left))
            if not block:break
            chunks.append(block);left-=len(block)
        after=os.fstat(fd);raw=b''.join(chunks)
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
                and len(raw)==before.st_size,'worker-readback')
        return raw
    finally:os.close(fd)


def exclusive(path,raw,mode=0o600):
    path=Path(path);safe(path.parent,directory=True)
    fd=os.open(path,os.O_WRONLY|os.O_EXCL|os.O_CREAT|os.O_NOFOLLOW,mode)
    directory=None
    try:
        offset=0
        while offset<len(raw):
            n=os.write(fd,raw[offset:]);require(n>0,'worker-write');offset+=n
        full_sync(fd,'file')
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        full_sync(directory,'directory')
    finally:
        close_quiet(fd);close_quiet(directory)
    require(read(path,len(raw))==raw,'worker-readback')


def capture(argv,end,hard,cap,*,limited=False):
    """Fixed argv, empty credential environment, bounded pipes and process-group reap."""
    require(os.name=='posix' and time.monotonic()<end<=hard,'worker-deadline')
    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,close_fds=True,start_new_session=not _IN_WORKER,
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C.UTF-8','TZ':'UTC'})
    selector=selectors.DefaultSelector();buffers=[bytearray(),bytearray()]
    timed_out=output_capped=False
    try:
        for i,stream in enumerate((process.stdout,process.stderr)):
            os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,i)
        while selector.get_map() or process.poll() is None:
            if time.monotonic()>=end:timed_out=True;break
            for key,_ in selector.select(min(.02,max(0,end-time.monotonic()))):
                block=os.read(key.fileobj.fileno(),65536)
                if not block:selector.unregister(key.fileobj);continue
                target=buffers[key.data];remaining=cap-len(target)
                target.extend(block[:remaining])
                if len(block)>remaining:output_capped=True;break
            if output_capped:break
        if not limited:require(not timed_out and not output_capped,'worker-command-limit')
    finally:
        try:
            if _IN_WORKER:process.kill()
            else:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        try:process.wait(timeout=max(0,hard-time.monotonic()))
        except subprocess.TimeoutExpired:raise Refused('worker-reap') from None
        selector.close();process.stdout.close();process.stderr.close()
        require(time.monotonic()<hard,'worker-deadline')
    return dict(rc=process.returncode,stdout=bytes(buffers[0]),stderr=bytes(buffers[1]),
                timed_out=timed_out,output_capped=output_capped)


def image(kind):return 'docker.io/library/eclipse-temurin@sha256:'+({'jdk':JDK,'jre':JRE}[kind])


def boundary(state,wanted,mounts):
    config,host=state['Config'],state['HostConfig']
    observed={x['Destination']:x for x in state['Mounts'] if x['Type']!='tmpfs'}
    require(config['Image']==wanted and config['User']=='65534:65534'
        and host['NetworkMode']=='none' and host['ReadonlyRootfs'] is True
        and host['PidsLimit']==64 and host['Memory']==512*1024*1024
        and host['NanoCpus']==1000000000 and host['CapDrop']==['ALL']
        and any(x.split(':')[0]=='no-new-privileges' for x in host['SecurityOpt'])
        and host['LogConfig']['Type']=='none' and not host.get('Privileged')
        and not host.get('Devices') and not host.get('Binds')
        and set(observed)==set(mounts),'worker-boundary')
    for destination,(source,rw,kind) in mounts.items():
        item=observed[destination]
        require(item['RW'] is rw and item['Type']==kind
            and (item.get('Name')==source if kind=='volume' else item['Source']==source),
            'worker-boundary')


def member(raw,name,cap):
    require(type(raw) is bytes and len(raw)<=cap+65536,'worker-archive-cap')
    try:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
            rows=list(archive)
            require(len(rows)==1,'worker-archive')
            row=rows[0]
            require(row.name==name and row.isfile() and not row.linkname
                and 0<=row.size<=cap,'worker-output-contract')
            result=archive.extractfile(row).read(cap+1)
            require(len(result)==row.size,'worker-archive')
            return result
    except (tarfile.TarError,EOFError,OSError):raise Refused('worker-archive') from None


class Docker:
    def __init__(self,prefix,root,end,hard):
        self.prefix,self.root,self.end,self.hard=prefix,Path(root),end,hard

    def call(self,args,cap=131072,*,limited=False):
        require(not list(Path(self.prefix[2]).iterdir()),'worker-docker-config')
        return capture([*self.prefix,*args],self.end,self.hard,cap,limited=limited)

    def ok(self,args,cap=131072):
        row=self.call(args,cap);require(row['rc']==0,'worker-docker');return row['stdout']

    def record(self,kind,name):
        require(kind in ('container','volume') and re.fullmatch(r'prw-[a-f0-9]{32}(?:-out)?',name),'worker-resource')
        exclusive(self.root/(kind+'-'+name+'.json'),c.canonical(dict(kind=kind,name=name)))

    def inspect(self,name):return json.loads(self.ok(['inspect',name]))[0]

    def preflight(self,kind):
        info=json.loads(self.ok(['info','--format','{"os":{{json .OSType}},"architecture":{{json .Architecture}}}']))
        require(info['os']=='linux' and info['architecture'] in ('aarch64','arm64'),'worker-platform')
        rows=json.loads(self.ok(['image','inspect',image(kind)]))
        digest=JDK if kind=='jdk' else JRE
        require(len(rows)==1 and rows[0]['Os']=='linux' and rows[0]['Architecture']=='arm64'
            and any(v in ('eclipse-temurin@sha256:'+digest,image(kind)) for v in rows[0]['RepoDigests']),
            'worker-image')

    def volume(self,name,size):
        self.record('volume',name)
        self.ok(['volume','create','--driver=local','--opt=type=tmpfs','--opt=device=tmpfs',
            '--opt=o=size='+size+',uid=65534,gid=65534,mode=0700',name])

    def create(self,name,kind,mounts,entry,args):
        self.record('container',name)
        flags=[]
        for dest,(source,rw,typ) in mounts.items():
            flags+=['--mount','type='+typ+',source='+source+',target='+dest+
                    (',volume-nocopy' if typ=='volume' else '')+('' if rw else ',readonly')]
        self.ok(['create','--name',name,*COMMON,'--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777',
                 *flags,'--entrypoint='+entry,image(kind),*args])
        boundary(self.inspect(name),image(kind),mounts)

    def collector(self,kind,volume,destination):
        # Keep the local-driver tmpfs mounted after the candidate exits. This
        # container executes no candidate code and has a read-only volume view.
        name='prw-'+uuid.uuid4().hex
        self.create(name,kind,{destination:(volume,False,'volume')},'/bin/sleep',['infinity'])
        self.ok(['start',name])
        state=self.inspect(name)['State']
        require(state['Running'] and not state['Error'],'worker-runtime-infrastructure')
        return name

    def collect_args(self,name,path):
        require(path in ('/build/javac.exit','/build/javac.stderr','/build/candidate.jar',
                         '/output/ACCTFILE.bin','/output/TRANSACT.bin'),'worker-copy')
        directory,leaf=path.rsplit('/',1)
        # Fixed trusted shell, no candidate-controlled interpolation. Exit 44
        # means absent (but a dangling symlink must still reach tar and refuse).
        script=('if [ ! -e "$1" ] && [ ! -L "$1" ]; then exit 44; fi; '
                'exec /bin/tar -C "$2" -cf - -- "$3"')
        return ['exec','--env','LC_ALL=C',name,'/bin/sh','-c',script,'sh',path,directory,leaf]

    def copy(self,name,path,cap,missing=False):
        row=self.call(self.collect_args(name,path),cap+65536)
        if row['rc']!=0:
            require(missing and row['rc']==44 and row['stdout']==row['stderr']==b'',
                    'worker-copy')
            return b''
        return member(row['stdout'],path.rsplit('/',1)[-1],cap)

    def prefix_copy(self,name,path,cap,missing=False):
        row=self.call(self.collect_args(name,path),cap+65536,limited=True)
        require(not row['timed_out'],'worker-deadline')
        if row['rc']!=0 and not row['output_capped']:
            require(missing and row['rc']==44 and row['stdout']==row['stderr']==b'',
                    'worker-copy')
            return b'',False
        try:
            with tarfile.open(fileobj=io.BytesIO(row['stdout']),mode='r:') as archive:
                item=archive.next()
                require(item is not None and item.isfile() and not item.linkname
                    and item.name==path.rsplit('/',1)[-1],'worker-output-contract')
                data=archive.extractfile(item).read(min(item.size,cap))
                require(len(data)==min(item.size,cap),'worker-archive')
                return data,item.size>cap or row['output_capped']
        except (tarfile.TarError,EOFError,OSError):raise Refused('worker-archive') from None

    def cleanup(self):
        self.end=self.hard-.02
        paths=sorted(self.root.glob('*.json'),key=lambda x:x.name.startswith('volume-'))
        require(len(paths)<=8,'worker-resource')
        receipts=[]
        for path in paths:
            if path.name.startswith('removed-'):continue
            row=json.loads(read(path,2048));kind,name=row['kind'],row['name']
            require(path.name==kind+'-'+name+'.json' and kind in ('container','volume')
                    and re.fullmatch(r'prw-[a-f0-9]{32}(?:-out)?',name),'worker-resource')
            args=['rm','--force','--volumes',name] if kind=='container' else ['volume','rm','--force',name]
            removed=self.call(args);marker=('no such '+kind).encode()
            require(removed['rc']==0 or removed['rc']==1 and marker in removed['stderr'].lower(),'worker-remove')
            absent=self.call([kind,'inspect',name])
            require(absent['rc']==1 and marker in absent['stderr'].lower(),'worker-absence')
            receipt=dict(kind=kind,name=name,absence_confirmed=True)
            exclusive(self.root/('removed-'+path.name),c.canonical(receipt));receipts.append(receipt)
        return receipts


COMPILE_SCRIPT = ('/usr/bin/sha256sum /opt/java/openjdk/bin/javac /opt/java/openjdk/bin/jar; '
    'mkdir /build/classes || exit 125; '
    '/opt/java/openjdk/bin/javac -XDrawDiagnostics -proc:none --release 21 -encoding UTF-8 '
    '-d /build/classes /source/Main.java /helper/RecordNumbers.java > /build/javac.stdout 2> /build/javac.stderr; '
    'rc=$?; printf "%s\\n" "$rc" > /build/javac.exit || exit 125; '
    'if [ "$rc" = 0 ]; then /opt/java/openjdk/bin/jar --create --file /build/candidate.jar '
    '--main-class Main -C /build/classes . || exit 125; fi; exit 0')


def compile_worker(req,docker):
    root=Path(req['root']);docker.preflight('jdk')
    require(c.sha(read(root/'Main.java',65536))==req['source_sha256'],'worker-source')
    require(c.sha(read(root/'RecordNumbers.java',65536))==req['helper_sha256'],'worker-helper')
    name='prw-'+uuid.uuid4().hex;volume=name+'-out';docker.volume(volume,'64m')
    collector=docker.collector('jdk',volume,'/build')
    mounts={'/source/Main.java':(str(root/'Main.java'),False,'bind'),
            '/helper/RecordNumbers.java':(str(root/'RecordNumbers.java'),False,'bind'),
            '/build':(volume,True,'volume')}
    docker.create(name,'jdk',mounts,'/bin/sh',['-c',COMPILE_SCRIPT])
    started=docker.call(['start','--attach',name])
    state=docker.inspect(name)['State']
    require(not state['Running'] and not state['Error'] and state['ExitCode']==0
            and started['rc']==0,'worker-build-infrastructure')
    require(started['stdout'].decode('ascii').splitlines()==[
        JAVAC+'  /opt/java/openjdk/bin/javac',JAR+'  /opt/java/openjdk/bin/jar'],'worker-tools')
    raw=docker.copy(collector,'/build/javac.exit',16)
    require(raw in (b'0\n',b'1\n'),'worker-javac-fault')
    exit_code=int(raw)
    stderr,_=docker.prefix_copy(collector,'/build/javac.stderr',65537)
    exclusive(root/'compiler.stderr',stderr)
    jar_hash=None
    if exit_code==0:
        jar=docker.copy(collector,'/build/candidate.jar',JAR_BYTES)
        require(bool(jar),'worker-jar');exclusive(root/'candidate.jar',jar,0o444);jar_hash=c.sha(jar)
    return dict(phase='javac',exit_code=exit_code,artifact_sha256=req['source_sha256'],
        jar_sha256=jar_hash,daemon_ok=True,image_match=True,tool_hash_match=True,timed_out=False,
        diagnostic_mode='javac-XDrawDiagnostics',stderr_sha256=c.sha(stderr))


def public_worker(req,docker):
    root=Path(req['root']);docker.preflight('jre')
    artifact=Path(req['artifact']);require(c.sha(read(artifact,JAR_BYTES))==req['jar_sha256'],'worker-artifact')
    for dd,digest in req['inputs'].items():
        require(dd in INPUTS and c.sha(read(root/'input'/(dd+'.bin'),DATA))==digest,'worker-input')
    require(re.fullmatch(r'\d{10}',req['processing_date']) and
        re.fullmatch(r'\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d{6}',req['timestamp']),'worker-clock')
    name='prw-'+uuid.uuid4().hex;volume=name+'-out';docker.volume(volume,'16m')
    collector=docker.collector('jre',volume,'/output')
    mounts={'/candidate.jar':(str(artifact),False,'bind'),'/input':(str(root/'input'),False,'bind'),
            '/output':(volume,True,'volume')}
    docker.create(name,'jre',mounts,'/opt/java/openjdk/bin/java',[
        '-Xmx256m','-jar','/candidate.jar','--input-dir','/input','--output-dir','/output',
        '--processing-date',req['processing_date'],'--timestamp',req['timestamp'],'--codec','cp037'])
    started=docker.call(['start','--attach',name],DATA,limited=True)
    # A limit is candidate DIFFERENT, but daemon/inspect/cleanup failures are faults.
    docker.end=docker.hard-.1
    if started['timed_out'] or started['output_capped']:
        killed=docker.call(['kill',name])
        require(killed['rc']==0 or b'is not running' in killed['stderr'].lower(),'worker-stop')
    state=docker.inspect(name)['State']
    require(not state['Running'] and not state['Error'] and state.get('StartedAt','')
            not in ('','0001-01-01T00:00:00Z'),
            'worker-runtime-infrastructure')
    observations=dict(stdout=started['stdout'],stderr=started['stderr'])
    for dd in OUTPUTS:
        observations[dd],capped=docker.prefix_copy(collector,'/output/'+dd+'.bin',DATA,missing=True)
        started['output_capped'] |= capped
    for channel,raw in observations.items():exclusive(root/('observed-'+channel),raw)
    return dict(exit=state['ExitCode'],timed_out=started['timed_out'],output_capped=started['output_capped'],
        artifact_sha256=req['source_sha256'],build_receipt_sha256=req['build_receipt_sha256'],
        observations={k:c.sha(v) for k,v in observations.items()})


def worker_main(path,expected):
    raw=read(path,32768);require(c.sha(raw)==expected,'worker-request')
    req=json.loads(raw)
    require(req['operation'] in ('compile','public') and all(type(req[k]) in (int,float)
        and math.isfinite(req[k]) for k in ('work_end','hard_end')),'worker-request')
    require(time.monotonic()<req['work_end']<req['hard_end'],'worker-deadline')
    root=safe(req['root'],directory=True);prefix=req['prefix']
    require(len(prefix)==5 and prefix[1]=='--config' and prefix[3]=='--host'
        and prefix[4].startswith('unix:///'),'worker-prefix')
    require(c.sha(read(prefix[0],64*1024*1024))==req['docker_sha256'],'worker-cli')
    docker=Docker(prefix,root/'resources',req['work_end'],req['hard_end'])
    result=compile_worker(req,docker) if req['operation']=='compile' else public_worker(req,docker)
    # Parent independently removes resources even when any preceding operation fails.
    return result


class PublicWorker:
    """Trusted launcher supplies authenticated CLI, endpoint and helper hashes.

    Parent directories are private; all child requests/observations are public.
    No held-out key or answer directory is accepted. Runtime profile is arm64.
    """
    def __init__(self,parent,run_id,docker_binary,docker_sha256,endpoint,helper,helper_sha256):
        require(os.name=='posix' and c.hash_ok(run_id) and c.hash_ok(docker_sha256)
                and c.hash_ok(helper_sha256),'worker-admission')
        root,fd,_=open_parent(parent);close_quiet(fd)
        self.root=root/('public-worker-'+run_id);self.root.mkdir(mode=0o700)
        self.config=self.root/'docker-config';self.config.mkdir(mode=0o700)
        binary=safe(docker_binary)
        require(c.sha(read(binary,64*1024*1024))==docker_sha256 and os.access(binary,os.X_OK),'worker-cli')
        require(type(endpoint) is str and endpoint.startswith('unix:///')
                and not any(x.isspace() for x in endpoint),'worker-endpoint')
        self.prefix=[str(binary),'--config',str(self.config),'--host',endpoint]
        self.docker_sha256=docker_sha256
        self.helper=read(helper,65536);require(c.sha(self.helper)==helper_sha256,'worker-helper')
        self.helper_sha256=helper_sha256;self.built={};self.next_build=0;self.next_case={};self.failed=False

    def _invoke(self,root,request,end,reserve):
        require(not self.failed and time.monotonic()+reserve<end,'worker-deadline')
        # Build has 30 seconds reserved; public cases have 5. Split that reserve
        # between child collection and independent parent remove/inspect.
        parent_reserve=15 if reserve==30 else 2.5
        request=dict(request,root=str(root),prefix=self.prefix,docker_sha256=self.docker_sha256,
                     work_end=end-reserve,hard_end=end-parent_reserve-.2)
        raw=json.dumps(request,sort_keys=True,allow_nan=False).encode()
        exclusive(root/'request.json',raw)
        (root/'resources').mkdir(mode=0o700)
        worker=Path(__file__).with_name('public_repair_worker_entry.py')
        outcome=None
        try:
            outcome=capture([sys.executable,'-I','-B',str(worker),str(root/'request.json'),c.sha(raw)],
                            end-parent_reserve-.1,end-parent_reserve,16384)
            if outcome['rc']!=0:
                token=outcome['stderr'].decode('ascii',errors='replace').strip()
                raise Refused(token if token in CODES else 'worker-child')
        finally:
            cleanup=Docker(self.prefix,root/'resources',end-.05,end).cleanup()
            exclusive(root/'cleanup.json',c.canonical(dict(removed=cleanup,cleanup=True)))
        require(time.monotonic()<end,'worker-deadline')
        value=json.loads(outcome['stdout'])
        receipt=dict(schema='public-worker-receipt/1',operation=request['operation'],
            result=value,cleanup_sha256=c.sha(read(root/'cleanup.json',65536)),
            cli_sha256=self.docker_sha256,helper_sha256=self.helper_sha256,
            jdk_sha256=JDK,jre_sha256=JRE,public_only=True)
        receipt_raw=c.canonical(receipt);exclusive(root/'receipt.json',receipt_raw)
        return value,c.sha(receipt_raw)

    def compile(self,source,round_no,deadline):
        try:
            require(type(round_no) is int and round_no==self.next_build<=5,'worker-build-order')
            self.next_build+=1
            c.text_ok(source,65536,73728);identity=c.sha(source.encode())
            root=self.root/('build-'+str(round_no));root.mkdir(mode=0o700)
            exclusive(root/'Main.java',source.encode(),0o444)
            exclusive(root/'RecordNumbers.java',self.helper,0o444)
            end=min(deadline,time.monotonic()+200)
            row,receipt=self._invoke(root,dict(operation='compile',source_sha256=identity,
                helper_sha256=self.helper_sha256),end,30)
            stderr=read(root/'compiler.stderr',65537)
            require(c.sha(stderr)==row.pop('stderr_sha256'),'worker-readback')
            jar_hash=row.pop('jar_sha256')
            if row['exit_code']==0:
                require(c.sha(read(root/'candidate.jar',JAR_BYTES))==jar_hash,'worker-jar')
                self.built[receipt]=(identity,root/'candidate.jar',jar_hash)
                self.next_case[receipt]=0
            return dict(row,stderr=stderr,receipt_sha256=receipt,cleanup=True)
        except BaseException:
            self.failed=True;raise

    def run_public(self,built,inputs,timestamp,processing_date,deadline,limits):
        try:
            require(not self.failed and built['build_receipt_sha256'] in self.built,'worker-build-join')
            receipt=built['build_receipt_sha256'];identity,artifact,jar_hash=self.built[receipt]
            require(built['artifact_sha256']==identity and built['status']=='BUILT','worker-build-join')
            try:
                check_public_limits(limits, deadline)
            except LimitsRefused as error:
                try:
                    exclusive(self.root/'worker-limits.json', c.canonical(error.evidence))
                except Exception:
                    # Evidence I/O must preserve the original refusal and its operands.
                    pass
                raise
            number=self.next_case[receipt];require(number<16,'worker-case-order');self.next_case[receipt]+=1
            root=self.root/('case-'+receipt[:16]+'-'+str(number));root.mkdir(mode=0o700)
            inp=root/'input';inp.mkdir(mode=0o755)
            require(type(inputs) is dict and set(inputs)==set(INPUTS),'worker-input')
            for dd,raw in inputs.items():
                require(type(raw) is bytes and len(raw)<=DATA,'worker-input')
                exclusive(inp/(dd+'.bin'),raw,0o444)
            req=dict(operation='public',source_sha256=identity,artifact=str(artifact),jar_sha256=jar_hash,
                build_receipt_sha256=receipt,inputs={k:c.sha(v) for k,v in inputs.items()},
                timestamp=timestamp,processing_date=processing_date)
            row,new_receipt=self._invoke(root,req,limits['cleanup_deadline'],
                limits['cleanup_deadline']-limits['execution_deadline'])
            observations={k:read(root/('observed-'+k),DATA) for k in (*OUTPUTS,'stdout','stderr')}
            require({k:c.sha(v) for k,v in observations.items()}==row.pop('observations'),'worker-readback')
            return dict(row,**observations,receipt_sha256=new_receipt,cleanup=True)
        except BaseException:
            self.failed=True;raise


def entry():
    global _IN_WORKER
    _IN_WORKER=True
    try:
        require(len(sys.argv)==3,'worker-arguments')
        result=worker_main(sys.argv[1],sys.argv[2])
        sys.stdout.buffer.write(c.canonical(result))
    except BaseException as error:
        token=str(error) if isinstance(error,Refused) and str(error) in CODES else 'worker-fault'
        sys.stderr.write(token+'\n')
        raise SystemExit(2) from None
