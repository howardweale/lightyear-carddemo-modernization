/* D01-A public CI feasibility probe. Never a production process owner. */
#ifdef __APPLE__
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <spawn.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern char **environ;
typedef int (*sandbox_init_fn)(const char *, unsigned long long, char **);
typedef void (*sandbox_free_fn)(char *);
static int witness = -1;
static sandbox_init_fn cached_init;
static sandbox_free_fn cached_release;
static int sandbox_rc = -99, relax_rc = -99, raise_rc = -99;
static int raise_error = 0;
static struct rlimit observed;

static void report(const char *kind, int error, int child, int status) {
    if (getrlimit(RLIMIT_NPROC, &observed) != 0) _exit(121);
    printf("{\"kind\":\"%s\",\"errno\":%d,\"child\":%d,\"wait_status\":%d,"
           "\"pid\":%d,\"uid\":%u,\"euid\":%u,\"soft\":%llu,\"hard\":%llu,"
           "\"sandbox_rc\":%d,\"relax_rc\":%d,\"raise_rc\":%d,"
           "\"raise_errno\":%d}\n", kind,error,child,status,getpid(),
           getuid(),geteuid(),(unsigned long long)observed.rlim_cur,
           (unsigned long long)observed.rlim_max,sandbox_rc,relax_rc,
           raise_rc,raise_error);
    fflush(stdout);
}
static int sandbox_policy(const char *profile) {
    if (!cached_init) {
        void *h = dlopen("/usr/lib/libsandbox.dylib", RTLD_NOW | RTLD_LOCAL);
        if (!h) return -98;
        cached_init = (sandbox_init_fn)dlsym(h, "sandbox_init");
        cached_release = (sandbox_free_fn)dlsym(h, "sandbox_free_error");
    }
    if (!cached_init || !cached_release) return -97;
    char *error = NULL;
    int rc = cached_init(profile, 0, &error);
    if (error) cached_release(error);
    /* Keep the library loaded: no post-policy loader activity is needed. */
    return rc;
}
static int policy(const char *name) {
    int limit = !strcmp(name,"rlimit") || !strcmp(name,"combined");
    int box = !strcmp(name,"sandbox") || !strcmp(name,"combined");
    if (limit) {
        struct rlimit zero = {0,0};
        if (setrlimit(RLIMIT_NPROC,&zero)) return errno;
        if (getrlimit(RLIMIT_NPROC,&observed)) return errno;
        if (observed.rlim_cur || observed.rlim_max) return EINVAL;
    }
    if (box) {
        /* Probe direct denial with no broad file/network/Mach allowance.
           Inherited IPC capabilities and production compatibility are unproved. */
        sandbox_rc = sandbox_policy("(version 1)(deny default)");
        if (sandbox_rc) return EPERM;
    }
    return 0;
}
static void reap(pid_t pid, int stopped) {
    int status = -1;
    if (stopped && kill(pid,SIGCONT)) {
        kill(pid,SIGKILL);
        waitpid(pid,&status,0);
        report("harness-error",errno,pid,status);
        exit(2);
    }
    pid_t got;
    do { got=waitpid(pid,&status,0); } while(got<0 && errno==EINTR);
    if (got!=pid || !WIFEXITED(status) || WEXITSTATUS(status)!=17) {
        report("harness-error",got<0?errno:EPROTO,pid,status);
        exit(2);
    }
    report("created",0,pid,status);
}
int main(int argc, char **argv) {
    if (argc!=4) return 2;
    witness=atoi(argv[3]);
    if (witness<3) return 2;
    alarm(8); /* Fixture backstop only; the outer observer owns its deadline. */
    if (!strcmp(argv[1],"sentinel")) {
        if (write(witness,"X",1)!=1) _exit(122);
        report("exec-entered",0,0,0);
        return 17;
    }
    if (getuid()==0 || geteuid()==0) {
        report("root-refused",EPERM,0,0);
        return 2;
    }
    if (strcmp(argv[1],"baseline") && strcmp(argv[1],"rlimit") &&
        strcmp(argv[1],"sandbox") && strcmp(argv[1],"combined")) return 2;
    char *child_args[]={argv[0],"sentinel","none",argv[3],NULL};
    /* Resolve and validate all probe inputs before applying the policy. */
    const char *op=argv[2];
    int e=policy(argv[1]);
    if (e) { report("policy-unavailable",e,0,0); return 2; }
    if (!strcmp(op,"raise-fork")) {
        struct rlimit one={1,1};
        errno=0; raise_rc=setrlimit(RLIMIT_NPROC,&one); raise_error=errno;
        op="fork";
    } else if (!strcmp(op,"relax-fork")) {
        relax_rc=sandbox_policy("(version 1)(allow default)");
        op="fork";
    }
    if (!strcmp(op,"fork") || !strcmp(op,"raw-fork")) {
        errno=0;
        pid_t pid=!strcmp(op,"fork")?fork():(pid_t)syscall(SYS_fork);
        e=errno;
        if (pid==0) {
            if (write(witness,"X",1)!=1) _exit(122);
            _exit(17);
        }
        if (pid<0) report("denied",e,0,0);
        else reap(pid,0);
    } else if (!strcmp(op,"vfork")) {
        errno=0;
        pid_t pid=vfork();
        if (pid==0) { execve(argv[0],child_args,environ); _exit(123); }
        e=errno;
        if (pid<0) report("denied",e,0,0);
        else reap(pid,0);
    } else if (!strcmp(op,"spawn") || !strcmp(op,"spawn-suspended") ||
               !strcmp(op,"spawn-setexec")) {
        posix_spawnattr_t attr;
        e=posix_spawnattr_init(&attr);
        if (e) { report("harness-error",e,0,0); return 2; }
        short flags=0;
        if (!strcmp(op,"spawn-suspended")) flags=POSIX_SPAWN_START_SUSPENDED;
        if (!strcmp(op,"spawn-setexec")) flags=POSIX_SPAWN_SETEXEC;
        e=posix_spawnattr_setflags(&attr,flags);
        if (e) { report("harness-error",e,0,0); return 2; }
        pid_t pid=-1;
        e=posix_spawn(&pid,argv[0],NULL,&attr,child_args,environ);
        posix_spawnattr_destroy(&attr);
        if(e) report("denied",e,0,0);
        else reap(pid,flags==POSIX_SPAWN_START_SUSPENDED);
    } else if (!strcmp(op,"exec")) {
        execve(argv[0],child_args,environ);
        report("denied",errno,0,0);
    } else { report("unknown-operation",EINVAL,0,0); return 2; }
    return 0;
}
#else
#error D01-A feasibility probe requires macOS CI
#endif
