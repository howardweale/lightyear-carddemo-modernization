/* CI-only library: invoked inside the already-bound worker, never a launcher.
 * Concurrent samples begin after entry. They do not cover installation races.
 * The owner's original deadline is the backstop; this library never renews it. */
#ifdef __APPLE__
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <mach/mach_time.h>
#include <pthread.h>
#include <stdatomic.h>
#include <spawn.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <time.h>
#include <math.h>

#define THREADS 4
#define ATTEMPTS 4
extern char **environ;
typedef int (*sandbox_init_fn)(const char *, unsigned long long, char **);
typedef void (*sandbox_free_fn)(char *);
struct result { int status, child, reaped, wait_status, resume_status, error, forced, kill_status; };
struct context {
    const char *executable;
    char **arguments;
    int witness, use_spawn;
    double original, cleanup, seconds_per_tick;
    atomic_int ready, release, abort_work;
    struct result results[THREADS][ATTEMPTS];
};
struct thread_argument { struct context *context; int id; };
static atomic_flag used = ATOMIC_FLAG_INIT;

static void child_witness(int fd) {
    if (write(fd, "X", 1) != 1) _exit(122);
    _exit(17);
}

/* Darwin's raw fork syscall carries a child flag outside its scalar result.
 * Uncached kernel PIDs distinguish the branch without libc getpid caching. */
static pid_t raw_fork(int *error) {
    long parent = syscall(SYS_getpid);
    if (parent <= 0) { *error = EPROTO; return -1; }
    long result = syscall(SYS_fork);
    int saved = errno;
    if (result >= 0) {
        long current = syscall(SYS_getpid);
        if (current <= 0) _exit(121);
        if (current != parent) result = 0;
    }
    errno = saved;
    return (pid_t)result;
}

static double now(const struct context *context) {
    /* CPython's macOS monotonic clock uses this same mach_absolute_time basis. */
    return (double)mach_absolute_time() * context->seconds_per_tick;
}

static void reap(struct context *context, struct result *r, pid_t child, int suspended) {
    r->child = child;
    if (suspended) {
        r->resume_status = kill(child, SIGCONT) == 0 ? 0 : errno;
        if (r->resume_status) {
            r->error = r->resume_status;
            r->forced = 1;
            r->kill_status = kill(child, SIGKILL) == 0 ? 0 : errno;
        }
    }
    for (;;) {
        pid_t got = waitpid(child, &r->wait_status, WNOHANG);
        if (got == child) { r->reaped = 1; break; }
        if (got < 0 && errno != EINTR) { r->error = errno; break; }
        double current = now(context);
        if (!r->forced && current >= context->original) {
            r->forced = 1;
            r->error = ETIMEDOUT;
            r->kill_status = kill(child, SIGKILL) == 0 ? 0 : errno;
        }
        if (current >= context->cleanup) { r->error = ETIMEDOUT; break; }
        struct timespec pause = {0, 1000000};
        nanosleep(&pause, NULL);
    }
    /* Preserve every raw wait status. The observer, not this library, judges it. */
}

static void create(struct context *context, const char *operation, struct result *r) {
    pid_t child = -1;
    r->wait_status = -1;
    r->resume_status = -1;
    r->kill_status = -1;
    if (now(context) >= context->original) { r->error = ETIMEDOUT; return; }
    errno = 0;
    if (!strcmp(operation, "fork") || !strcmp(operation, "raw-fork")) {
        child = !strcmp(operation, "fork") ? fork() : raw_fork(&r->error);
        r->status = child < 0 ? errno : 0;
        if (!child) child_witness(context->witness);
    } else if (!strcmp(operation, "vfork")) {
        /* Prepare argv before vfork. No Python, allocation, logging or witness
         * call in the shared-address-space child: only execve or _exit. */
        child = vfork();
        if (!child) { execve(context->executable, context->arguments, environ); _exit(123); }
        r->status = child < 0 ? errno : 0;
    } else {
        posix_spawnattr_t attributes;
        int error = posix_spawnattr_init(&attributes);
        if (error) { r->error = error; return; }
        short flags = !strcmp(operation, "spawn-suspended") ? POSIX_SPAWN_START_SUSPENDED :
                      !strcmp(operation, "spawn-setexec") ? POSIX_SPAWN_SETEXEC : 0;
        error = posix_spawnattr_setflags(&attributes, flags);
        if (error) r->error = error;
        else r->status = posix_spawn(&child, context->executable, NULL, &attributes,
                                     context->arguments, environ);
        error = posix_spawnattr_destroy(&attributes);
        if (error) r->error = error;
        if (r->status) child = -1;
    }
    if (child > 0) reap(context, r, child, !strcmp(operation, "spawn-suspended"));
}

static void *thread_attempts(void *argument) {
    struct thread_argument *item = argument;
    struct context *context = item->context;
    atomic_fetch_add_explicit(&context->ready, 1, memory_order_release);
    while (!atomic_load_explicit(&context->release, memory_order_acquire)) {
        struct timespec pause = {0, 1000000};
        nanosleep(&pause, NULL);
    }
    if (atomic_load_explicit(&context->abort_work, memory_order_acquire)) return NULL;
    for (int i = 0; i < ATTEMPTS; i++)
        create(context, context->use_spawn ? "spawn" : "fork", &context->results[item->id][i]);
    return NULL;
}

static int concurrent(struct context *context) {
    pthread_t threads[THREADS];
    struct thread_argument arguments[THREADS];
    int count = 0, error = 0;
    for (int i = 0; i < THREADS; i++) {
        arguments[i] = (struct thread_argument){context, i};
        error = pthread_create(&threads[i], NULL, thread_attempts, &arguments[i]);
        if (error) break;
        count++;
    }
    if (error) atomic_store_explicit(&context->abort_work, 1, memory_order_release);
    while (atomic_load_explicit(&context->ready, memory_order_acquire) != count) {
        if (now(context) >= context->original) {
            error = ETIMEDOUT;
            atomic_store_explicit(&context->abort_work, 1, memory_order_release);
            break;
        }
        struct timespec pause = {0, 1000000};
        nanosleep(&pause, NULL);
    }
    atomic_store_explicit(&context->release, 1, memory_order_release);
    for (int i = 0; i < count; i++) {
        /* Never return stack-backed state while a thread may still reference it. */
        if (pthread_join(threads[i], NULL)) _exit(120);
    }
    return error;
}

static int append(char **cursor, size_t *remaining, const char *format, ...) {
    va_list arguments;
    va_start(arguments, format);
    int count = vsnprintf(*cursor, *remaining, format, arguments);
    va_end(arguments);
    if (count < 0 || (size_t)count >= *remaining) return ENOSPC;
    *cursor += count;
    *remaining -= (size_t)count;
    return 0;
}

int d01_attempt(const char *operation, const char *interpreter, int witness_fd,
                double original, double cleanup, char *json, size_t capacity) {
    static const char *allowed[] = {"raw-fork", "vfork", "spawn-suspended", "spawn-setexec",
        "raise-fork", "relax-fork", "concurrent-fork", "concurrent-spawn"};
    if (!operation || !interpreter || !json || capacity < 8192 || interpreter[0] != '/' ||
        witness_fd < 3 || witness_fd > 1024 || !getuid() || !geteuid() ||
        !isfinite(original) || !isfinite(cleanup) || cleanup != original + 5.0) return EINVAL;
    int known = 0;
    for (size_t i = 0; i < sizeof(allowed)/sizeof(allowed[0]); i++)
        if (!strcmp(operation, allowed[i])) known = 1;
    if (!known) return EINVAL;
    struct stat descriptor;
    if (fstat(witness_fd, &descriptor) || !S_ISFIFO(descriptor.st_mode)) return EINVAL;
    if (atomic_flag_test_and_set_explicit(&used, memory_order_acq_rel)) return EALREADY;
    struct rlimit before, after, requested = {0, 0};
    if (getrlimit(RLIMIT_NPROC, &before)) return errno;
    char sentinel[1024];
    const char *sentinel_format = !strcmp(operation, "spawn-setexec") ?
        "import os,json,resource,sys;print(json.dumps(dict(kind='d01-replacement',"
        "operation='spawn-setexec',pid=os.getpid(),parent_pid=os.getppid(),"
        "interpreter=os.path.realpath(sys.executable),"
        "nproc=list(resource.getrlimit(resource.RLIMIT_NPROC)))),flush=True);"
        "os._exit(17 if os.write(%d,b'X')==1 else 122)" :
        "import os;os._exit(17 if os.write(%d,b'X')==1 else 122)";
    int length = snprintf(sentinel, sizeof(sentinel), sentinel_format, witness_fd);
    if (length < 0 || (size_t)length >= sizeof(sentinel)) return ENOSPC;
    char *arguments[] = {(char *)interpreter, "-I", "-B", "-c", sentinel, NULL};
    mach_timebase_info_data_t timebase;
    if (mach_timebase_info(&timebase) != KERN_SUCCESS || !timebase.denom) return EPROTO;
    struct context context = {.executable=interpreter, .arguments=arguments, .witness=witness_fd,
        .original=original, .cleanup=cleanup,
        .seconds_per_tick=(double)timebase.numer/(double)timebase.denom/1000000000.0};
    if (now(&context) >= original) return ETIMEDOUT;
    atomic_init(&context.ready, 0);
    atomic_init(&context.release, 0);
    atomic_init(&context.abort_work, 0);
    int raise_rc = -99, raise_error = 0, relax_rc = -99, relax_error = 0, internal = 0;
    const char *creation = operation;
    if (!strcmp(operation, "raise-fork")) {
        /* Baseline sets both limits to its existing positive soft limit. Combined
         * attempts 0 -> 1. The numeric requests differ and are reported exactly. */
        requested.rlim_cur = requested.rlim_max = before.rlim_cur ? before.rlim_cur : 1;
        errno = 0;
        raise_rc = setrlimit(RLIMIT_NPROC, &requested);
        raise_error = raise_rc ? errno : 0;
        creation = "fork";
    } else if (!strcmp(operation, "relax-fork")) {
        void *library = dlopen("/usr/lib/libsandbox.dylib", RTLD_NOW | RTLD_LOCAL);
        if (!library) return ENOENT;
        sandbox_init_fn init = (sandbox_init_fn)dlsym(library, "sandbox_init");
        sandbox_free_fn release = (sandbox_free_fn)dlsym(library, "sandbox_free_error");
        if (!init || !release) return ENOSYS;
        char *error = NULL;
        errno = 0;
        relax_rc = init("(version 1)(allow default)", 0, &error);
        relax_error = relax_rc ? errno : 0;
        if (error) release(error);
        /* Keep the library loaded. A successful call does not show relaxation:
         * sandbox layers may intersect, and zero NPROC independently masks it. */
        creation = "fork";
    }
    int threads = !strncmp(operation, "concurrent-", 11) ? THREADS : 1;
    int attempts = threads == THREADS ? ATTEMPTS : 1;
    if (threads == THREADS) {
        context.use_spawn = !strcmp(operation, "concurrent-spawn");
        internal = concurrent(&context);
    } else create(&context, creation, &context.results[0][0]);
    if (getrlimit(RLIMIT_NPROC, &after)) return errno;
    for (int t = 0; t < threads; t++) for (int i = 0; i < attempts; i++)
        if (context.results[t][i].error) internal = context.results[t][i].error;
    char *cursor = json;
    size_t remaining = capacity;
    int error = append(&cursor, &remaining,
        "{\"operation\":\"%s\",\"pid\":%d,\"parent_pid\":%d,"
        "\"nproc_before\":[%llu,%llu],\"nproc_after\":[%llu,%llu],"
        "\"requested_nproc\":[%llu,%llu],\"raise_rc\":%d,\"raise_errno\":%d,"
        "\"relax_rc\":%d,\"relax_errno\":%d,\"ready_threads\":%d,"
        "\"internal_error\":%d,\"attempts\":[", operation, getpid(), getppid(),
        (unsigned long long)before.rlim_cur, (unsigned long long)before.rlim_max,
        (unsigned long long)after.rlim_cur, (unsigned long long)after.rlim_max,
        (unsigned long long)requested.rlim_cur, (unsigned long long)requested.rlim_max,
        raise_rc, raise_error, relax_rc, relax_error, atomic_load(&context.ready), internal);
    if (error) return error;
    for (int t = 0; t < threads; t++) for (int i = 0; i < attempts; i++) {
        struct result *r = &context.results[t][i];
        char child[32], wait_status[32], resume_status[32];
        if (r->child > 0) snprintf(child, sizeof(child), "%d", r->child);
        else snprintf(child, sizeof(child), "null");
        if (r->reaped) snprintf(wait_status, sizeof(wait_status), "%d", r->wait_status);
        else snprintf(wait_status, sizeof(wait_status), "null");
        if (r->resume_status >= 0) snprintf(resume_status, sizeof(resume_status), "%d", r->resume_status);
        else snprintf(resume_status, sizeof(resume_status), "null");
        error = append(&cursor, &remaining,
            "%s{\"thread\":%d,\"iteration\":%d,\"status\":%d,\"child\":%s,"
            "\"reaped\":%s,\"wait_status\":%s,\"resume_status\":%s,\"error\":%d,"
            "\"forced\":%s,\"kill_status\":%d}",
            t || i ? "," : "", t, i, r->status, child, r->reaped ? "true" : "false",
            wait_status, resume_status, r->error, r->forced ? "true" : "false", r->kill_status);
        if (error) return error;
    }
    return append(&cursor, &remaining, "]}");
}
#else
#error D01 bound-worker regression requires macOS CI
#endif
