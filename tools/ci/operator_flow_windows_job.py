"""Windows process-lifetime kernel for a separately reviewed publisher launcher.

No approval, GitHub operation, proof, intent or retry entry. The owner must fix
and authenticate the child command and environment. CI uses inert children.
Job membership is lifetime/resource containment, not a security sandbox.
"""
import math
import os
from pathlib import Path
import subprocess
import time


def _limits(command, cwd, env, timeout, max_bytes, memory_bytes, process_limit):
    if (type(command) not in (list, tuple) or not command
            or any(type(x) is not str or not x or '\0' in x for x in command)
            or not Path(command[0]).is_absolute()):
        raise ValueError('publisher-job-command')
    if len(subprocess.list2cmdline(command).encode('utf-16-le')) > 65532:
        raise ValueError('publisher-job-command')
    if type(cwd) not in (str, Path) and not isinstance(cwd, Path):
        raise ValueError('publisher-job-cwd')
    if not Path(cwd).is_absolute():
        raise ValueError('publisher-job-cwd')
    if '\0' in str(cwd) or len(str(cwd)) > 32760:
        raise ValueError('publisher-job-cwd')
    if (type(env) is not dict or not env
            or any(type(k) is not str or type(v) is not str or not k
                   or '=' in k or '\0' in k or '\0' in v for k, v in env.items())
            or len({k.casefold() for k in env}) != len(env)):
        raise ValueError('publisher-job-environment')
    if sum(len((k+'='+v+'\0').encode('utf-16-le')) for k,v in env.items()) > 65530:
        raise ValueError('publisher-job-environment')
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 2400
            or type(max_bytes) is not int or not 0 < max_bytes <= 4*1024*1024
            or type(memory_bytes) is not int or not 64*1024*1024 <= memory_bytes <= 4*1024**3
            or type(process_limit) is not int or not 1 <= process_limit <= 32):
        raise ValueError('publisher-job-limits')


def run_contained(command, *, cwd, env, timeout, max_bytes,
                  memory_bytes, process_limit):
    """Return the original CompletedProcess only after job quiescence and EOF.

    Creation is atomic with job assignment. No shell, stdin, stderr capture,
    breakaway, command retry, generic process kill, injected API or clock.
    OS creation/termination calls are not a universal wall-clock guarantee.
    """
    _limits(command, cwd, env, timeout, max_bytes, memory_bytes, process_limit)
    if os.name != 'nt':
        raise ValueError('publisher-job-windows-only')
    import ctypes as c
    from ctypes import wintypes as w
    if c.sizeof(c.c_void_p) != 8:
        raise ValueError('publisher-job-64-bit-required')
    H=w.HANDLE;D=w.DWORD;S=c.c_size_t;P=c.c_void_p
    class SA(c.Structure):
        _fields_=[('size',D),('descriptor',P),('inherit',w.BOOL)]
    class Basic(c.Structure):
        _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),
            ('flags',D),('minimum',S),('maximum',S),('active',D),
            ('affinity',S),('priority',D),('scheduling',D)]
    class IO(c.Structure):
        _fields_=[(n,c.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class Extended(c.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',S),('job_memory',S),
            ('peak_process',S),('peak_job',S)]
    class Accounting(c.Structure):
        _fields_=[(n,c.c_longlong) for n in ('user','kernel','period_user','period_kernel')]+[
            ('faults',D),('total',D),('active',D),('terminated',D)]
    class Startup(c.Structure):
        _fields_=[('cb',D),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR),
            ('x',D),('y',D),('xsize',D),('ysize',D),('xchars',D),('ychars',D),
            ('fill',D),('flags',D),('show',w.WORD),('reserved_size',w.WORD),
            ('reserved_bytes',P),('stdin',H),('stdout',H),('stderr',H)]
    class StartupEx(c.Structure):
        _fields_=[('startup',Startup),('attributes',P)]
    class ProcessInfo(c.Structure):
        _fields_=[('process',H),('thread',H),('pid',D),('tid',D)]
    k=c.WinDLL('kernel32',use_last_error=True)
    signatures={
        'CreateJobObjectW':([P,w.LPCWSTR],H),
        'SetInformationJobObject':([H,c.c_int,P,D],w.BOOL),
        'QueryInformationJobObject':([H,c.c_int,P,D,P],w.BOOL),
        'TerminateJobObject':([H,w.UINT],w.BOOL),
        'CreatePipe':([c.POINTER(H),c.POINTER(H),P,D],w.BOOL),
        'SetHandleInformation':([H,D,D],w.BOOL),
        'CreateFileW':([w.LPCWSTR,D,D,P,D,D,H],H),
        'InitializeProcThreadAttributeList':([P,D,D,c.POINTER(S)],w.BOOL),
        'UpdateProcThreadAttribute':([P,D,S,P,S,P,P],w.BOOL),
        'DeleteProcThreadAttributeList':([P],None),
        'CreateProcessW':([w.LPCWSTR,w.LPWSTR,P,P,w.BOOL,D,P,w.LPCWSTR,P,P],w.BOOL),
        'PeekNamedPipe':([H,P,D,P,c.POINTER(D),P],w.BOOL),
        'ReadFile':([H,P,D,c.POINTER(D),P],w.BOOL),
        'GetExitCodeProcess':([H,c.POINTER(D)],w.BOOL),
        'IsProcessInJob':([H,H,c.POINTER(w.BOOL)],w.BOOL),
        'CloseHandle':([H],w.BOOL)}
    for name,(args,result) in signatures.items():
        f=getattr(k,name);f.argtypes=args;f.restype=result
    def check(value, reason):
        if not value:raise ValueError(reason)
    handles=[];job=None;attributes=None;initialized=False;launched=False;quiet=False
    info=ProcessInfo();data=bytearray()
    deadline=time.monotonic()+timeout
    def own(handle):
        check(handle and handle != c.c_void_p(-1).value,'publisher-job-handle')
        handles.append(handle);return handle
    def close(handle):
        check(k.CloseHandle(handle),'publisher-job-close')
        handles.remove(handle)
    def active():
        a=Accounting()
        check(k.QueryInformationJobObject(job,1,c.byref(a),c.sizeof(a),None),'publisher-job-accounting')
        return a.active
    try:
        job=own(k.CreateJobObjectW(None,None))
        limits=Extended()
        # KILL_ON_JOB_CLOSE | JOB_MEMORY | ACTIVE_PROCESS; never BREAKAWAY.
        limits.basic.flags=0x2000|0x200|0x8
        limits.basic.active=process_limit;limits.job_memory=memory_bytes
        check(k.SetInformationJobObject(job,9,c.byref(limits),c.sizeof(limits)),'publisher-job-resource-limit')
        sa=SA(c.sizeof(SA),None,True)
        read=H();write=H()
        check(k.CreatePipe(c.byref(read),c.byref(write),c.byref(sa),65536),'publisher-job-pipe')
        own(read.value);own(write.value)
        check(k.SetHandleInformation(read,1,0),'publisher-job-read-inheritance')
        null=own(k.CreateFileW('NUL',0x80000000|0x40000000,3,c.byref(sa),3,0,None))
        size=S()
        # Expected first call determines the native allocation size.
        k.InitializeProcThreadAttributeList(None,2,0,c.byref(size))
        check(0<size.value<=65536,'publisher-job-attribute-size')
        attributes=c.create_string_buffer(size.value)
        check(k.InitializeProcThreadAttributeList(attributes,2,0,c.byref(size)),'publisher-job-attributes')
        initialized=True
        jobs=(H*1)(job);inherited=(H*2)(write.value,null)
        check(k.UpdateProcThreadAttribute(attributes,0,0x2000D,jobs,c.sizeof(jobs),None,None),
              'publisher-job-atomic-assignment')
        check(k.UpdateProcThreadAttribute(attributes,0,0x20002,inherited,c.sizeof(inherited),None,None),
              'publisher-job-handle-list')
        start=StartupEx();start.startup.cb=c.sizeof(start)
        start.startup.flags=0x100|0x1;start.startup.show=0
        start.startup.stdin=null;start.startup.stdout=write.value;start.startup.stderr=null
        start.attributes=c.cast(attributes,P)
        block=c.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items(),key=lambda item:item[0].casefold()))+'\0\0')
        cmd=c.create_unicode_buffer(subprocess.list2cmdline(command))
        # EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW.
        check(k.CreateProcessW(command[0],cmd,None,None,True,0x80000|0x400|0x8000000,
              block,str(cwd),c.byref(start),c.byref(info)),'publisher-job-create')
        launched=True;own(info.process);own(info.thread)
        close(info.thread);close(write.value);close(null)
        member=w.BOOL()
        check(k.IsProcessInJob(info.process,job,c.byref(member)) and member.value,'publisher-job-membership')
        eof=False
        while True:
            if time.monotonic()>=deadline:raise ValueError('publisher-job-timeout')
            available=D()
            if not eof and not k.PeekNamedPipe(read,None,0,None,c.byref(available),None):
                if c.get_last_error()==109:eof=True
                else:raise ValueError('publisher-job-peek')
            if available.value:
                amount=min(65536,available.value,max_bytes+1-len(data))
                buf=c.create_string_buffer(amount);got=D()
                check(k.ReadFile(read,buf,amount,c.byref(got),None),'publisher-job-read')
                data.extend(buf.raw[:got.value])
                if len(data)>max_bytes:raise ValueError('publisher-job-output-limit')
            if active()==0:
                quiet=True
                if eof:
                    code=D();check(k.GetExitCodeProcess(info.process,c.byref(code)),'publisher-job-exit')
                    return subprocess.CompletedProcess(tuple(command),code.value,bytes(data),None)
            time.sleep(0.01)
    finally:
        # Terminate only this job. Unknown cleanup never becomes success.
        cleanup_failed=False
        if launched and not quiet:
            if not k.TerminateJobObject(job,1):cleanup_failed=True
            end=time.monotonic()+5
            try:
                while active():
                    if time.monotonic()>=end:
                        cleanup_failed=True;break
                    time.sleep(0.01)
            except Exception:cleanup_failed=True
        if initialized:k.DeleteProcThreadAttributeList(attributes)
        for h in reversed(handles):
            if not k.CloseHandle(h):cleanup_failed=True
        if cleanup_failed:raise ValueError('publisher-job-quiescence-unavailable')
