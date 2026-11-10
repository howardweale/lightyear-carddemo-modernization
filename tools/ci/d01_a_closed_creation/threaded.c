/* Public concurrent fork/spawn samples, not production containment proof. */
#ifdef __APPLE__
#include <sys/resource.h>
#include <sys/wait.h>
#include <pthread.h>
#include <stdatomic.h>
#include <spawn.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define THREADS 4
#define ATTEMPTS 4
extern char **environ;
typedef int (*sandbox_init_fn)(const char *, unsigned long long, char **);
struct result { int status, child, reaped, wait_status; };
static struct result results[THREADS][ATTEMPTS];
static atomic_int ready_count, release_work;
static int witness, use_spawn;
static char **sentinel_args;
static char *executable;

static void *attempts(void *argument) {
    int thread = *(int *)argument;
    atomic_fetch_add_explicit(&ready_count, 1, memory_order_release);
    while (!atomic_load_explicit(&release_work, memory_order_acquire)) {
        struct timespec pause = {0, 1000000};
        nanosleep(&pause, NULL);
    }
    for (int i = 0; i < ATTEMPTS; i++) {
        struct result *r = &results[thread][i];
        pid_t child = -1;
        if (use_spawn) {
            r->status = posix_spawn(&child, executable, NULL, NULL, sentinel_args, environ);
        } else {
            errno = 0;
            child = fork();
            r->status = child < 0 ? errno : 0;
            if (!child) {
                /* Only async-signal-safe operations in this multithreaded child. */
                if (write(witness, "X", 1) != 1) _exit(122);
                _exit(17);
            }
        }
        if (child > 0) {
            r->child = child;
            pid_t got;
            do { got = waitpid(child, &r->wait_status, 0); } while (got < 0 && errno == EINTR);
            r->reaped = got == child && WIFEXITED(r->wait_status) && WEXITSTATUS(r->wait_status) == 17;
        }
    }
    return NULL;
}

static void start_threads(pthread_t *threads, int *ids) {
    for (int i = 0; i < THREADS; i++) {
        ids[i] = i;
        if (pthread_create(&threads[i], NULL, attempts, &ids[i])) _exit(120);
    }
    while (atomic_load_explicit(&ready_count, memory_order_acquire) != THREADS) {
        struct timespec pause = {0, 1000000};
        nanosleep(&pause, NULL);
    }
}

int main(int argc, char **argv) {
    if (argc != 5) return 2;
    char *tail = NULL;
    long fd = strtol(argv[4], &tail, 10);
    if (!tail || *tail || fd < 3 || fd > 1024) return 2;
    witness = (int)fd;
    alarm(8);
    if (!strcmp(argv[1], "sentinel")) {
        if (write(witness, "X", 1) != 1) _exit(122);
        return 17;
    }
    if (!getuid() || !geteuid()) return 2;
    int combined = !strcmp(argv[1], "combined");
    int before = !strcmp(argv[2], "threads-before-policy");
    if ((!combined && strcmp(argv[1], "baseline")) ||
        (!before && strcmp(argv[2], "threads-after-policy")) ||
        (strcmp(argv[3], "fork") && strcmp(argv[3], "spawn"))) return 2;
    use_spawn = !strcmp(argv[3], "spawn");
    executable = argv[0];
    char *child_args[] = {argv[0], "sentinel", "none", "none", argv[4], NULL};
    sentinel_args = child_args;
    /* Resolve trusted policy entrypoint before any worker threads exist. */
    void *library = dlopen("/usr/lib/libsandbox.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!library) return 2;
    sandbox_init_fn sandbox_init = (sandbox_init_fn)dlsym(library, "sandbox_init");
    if (!sandbox_init) return 2;
    pthread_t threads[THREADS];
    int ids[THREADS];
    if (before) start_threads(threads, ids);
    int sandbox_rc = -99;
    struct rlimit limit;
    if (combined) {
        struct rlimit zero = {0, 0};
        if (setrlimit(RLIMIT_NPROC, &zero)) return 2;
        char *error = NULL;
        sandbox_rc = sandbox_init("(version 1)(deny default)", 0, &error);
        /* No release: process lifetime bounds the error buffer/library. */
        if (sandbox_rc) return 2;
    }
    if (getrlimit(RLIMIT_NPROC, &limit) || (combined && (limit.rlim_cur || limit.rlim_max))) return 2;
    if (!before) start_threads(threads, ids);
    /* Work release is AFTER the policy; no sample is excused as a transition race. */
    atomic_store_explicit(&release_work, 1, memory_order_release);
    for (int i = 0; i < THREADS; i++) if (pthread_join(threads[i], NULL)) return 2;
    if (getrlimit(RLIMIT_NPROC, &limit)) return 2;
    printf("{\"pid\":%d,\"uid\":%u,\"euid\":%u,\"sandbox_rc\":%d,"
           "\"nproc\":[%llu,%llu],\"ready_threads\":%d,\"attempts\":[",
           getpid(), getuid(), geteuid(), sandbox_rc,
           (unsigned long long)limit.rlim_cur, (unsigned long long)limit.rlim_max,
           atomic_load(&ready_count));
    for (int t = 0; t < THREADS; t++) for (int i = 0; i < ATTEMPTS; i++) {
        struct result *r = &results[t][i];
        printf("%s{\"thread\":%d,\"iteration\":%d,\"status\":%d,\"child\":%d,"
               "\"reaped\":%d,\"wait_status\":%d}", t || i ? "," : "",
               t, i, r->status, r->child, r->reaped, r->wait_status);
    }
    puts("]}");
    return 0;
}
#else
#error D01-A thread samples require macOS CI
#endif
