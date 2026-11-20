/* NO-KEY prototype pre-exec launcher. Never production containment proof. */
#ifdef __APPLE__
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <mach/mach_time.h>

typedef int (*sandbox_init_fn)(const char *, unsigned long long, char **);
static void fail(void) { _exit(125); }

static void canonical(const char *value, char *out, int directory) {
    struct stat st;
    if (!realpath(value, out) || strcmp(value, out) || stat(out, &st)) fail();
    if (directory ? !S_ISDIR(st.st_mode) : !S_ISREG(st.st_mode)) fail();
    for (const unsigned char *p = (const unsigned char *)out; *p; p++)
        if (*p < 32 || *p == '"' || *p == '\\') fail();
}
static int beneath(const char *path, const char *root) {
    size_t n = strlen(root);
    return n > 1 && !strncmp(path, root, n) && path[n] == '/';
}
static double now(void) {
    mach_timebase_info_data_t info;
    if (mach_timebase_info(&info) != 0 || !info.denom) fail();
    return (double)mach_absolute_time() * info.numer / info.denom / 1000000000.0;
}
int main(int argc, char **argv) {
    /* mode runtime app interpreter -I -B worker --worker child S? clocks
       --d01-probe operation witness-fd app; no shell or arbitrary launch flags. */
    if ((argc != 17 && argc != 19) || getuid() == 0 || geteuid() == 0) fail();
    if (argc == 19) {
        if (strcmp(argv[17], "--d01-native-sha256") || strlen(argv[18]) != 64 ||
            strspn(argv[18], "0123456789abcdef") != 64) fail();
    }
    int combined = !strcmp(argv[1], "combined");
    if (!combined && strcmp(argv[1], "baseline")) fail();
    if (strcmp(argv[5], "-I") || strcmp(argv[6], "-B") ||
        strcmp(argv[8], "--worker") || strcmp(argv[9], "child") ||
        (strcmp(argv[10], "S1") && strcmp(argv[10], "S2")) ||
        strcmp(argv[13], "--d01-probe") || strcmp(argv[3], argv[16])) fail();
    const char *operations[] = {"none", "fork", "spawn", "exec-same",
                                "exec-other", "mach-lookup", "ls-open",
        "raw-fork", "vfork", "spawn-suspended", "spawn-setexec",
        "raise-fork", "relax-fork", "concurrent-fork", "concurrent-spawn"};
    int known = 0;
    for (unsigned i = 0; i < sizeof(operations)/sizeof(operations[0]); i++)
        if (!strcmp(argv[14], operations[i])) known = 1;
    if (!known) fail();
    if (argc != 19) {
        for (unsigned i = 7; i < sizeof(operations)/sizeof(operations[0]); i++)
            if (!strcmp(argv[14], operations[i])) fail();
    }
    char *end = NULL;
    double original = strtod(argv[11], &end);
    if (!end || *end || !isfinite(original)) fail();
    double cleanup = strtod(argv[12], &end);
    if (!end || *end || !isfinite(cleanup) || cleanup != original + 5 ||
        now() >= original || original - now() > 60) fail();
    long fd = strtol(argv[15], &end, 10);
    if (!end || *end || fd < 3 || fd > 1024) fail();
    char runtime[PATH_MAX], app[PATH_MAX], interpreter[PATH_MAX], worker[PATH_MAX];
    char probe[PATH_MAX], candidate[PATH_MAX];
    canonical(argv[2], runtime, 1);
    canonical(argv[3], app, 1);
    canonical(argv[4], interpreter, 0);
    canonical(argv[7], worker, 0);
    if (!beneath(interpreter, runtime) || !strcmp(runtime, "/usr") ||
        !strcmp(runtime, "/System") || !strcmp(runtime, "/Library")) fail();
    const char *leaf = strrchr(worker, '/');
    if (!leaf || strcmp(leaf + 1, "mac_owner_process.py")) fail();
    int n = snprintf(candidate, sizeof(candidate), "%.*s/mac_owner_preexec_probe.py",
                     (int)(leaf-worker), worker);
    if (n < 0 || (size_t)n >= sizeof(candidate)) fail();
    canonical(candidate, probe, 0);
    /* Public runtime reads only: exact worker/probe, selected Python runtime,
       immutable system dynamic-loader/framework roots, and disposable app input.
       No home, checkout root, general temp, write, network or process-fork grant. */
    char profile[PATH_MAX * 6 + 1024];
    n = snprintf(profile, sizeof(profile),
        "(version 1)(deny default)"
        "(allow sysctl-read (sysctl-name \"kern.ostype\"))"
        "(allow sysctl-read (sysctl-name \"kern.osrelease\"))"
        "(allow sysctl-read (sysctl-name \"kern.version\"))"
        "(allow sysctl-read (sysctl-name \"kern.hostname\"))"
        "(allow sysctl-read (sysctl-name \"hw.machine\"))"
        "(allow sysctl-read (sysctl-name \"kern.osproductversion\"))"
        "(allow sysctl-read (sysctl-name \"kern.osvariant_status\"))"
        "(allow sysctl-read (sysctl-name \"kern.secure_kernel\"))"
        "(allow sysctl-read (sysctl-name \"hw.ephemeral_storage\"))"
        "(allow sysctl-read (sysctl-name \"hw.optional.armv8_2_sha512\"))"
        "(allow sysctl-read (sysctl-name \"hw.optional.armv8_2_sha3\"))"
        "(allow file-read-metadata (literal \"/\"))"
        "(allow file-read-metadata (literal \"/Users\"))"
        "(allow file-read-metadata (literal \"/Users/runner\"))"
        "(allow file-read-metadata (literal \"/Users/runner/work\"))"
        "(allow file-read-metadata (literal \"/Users/runner/work/_temp\"))"
        "(allow file-read-metadata (literal \"/var\"))"
        "(allow file-read-metadata (literal \"/etc\"))"
        "(allow file-read-metadata (literal \"/System/Cryptexes/OS\"))"
        "(allow file-read-data (literal \"/private/etc/ssl/openssl.cnf\"))"
        "(allow file-read-data (literal \"/dev/dtracehelper\"))"
        "(allow file-read-data (literal \"/\"))"
        "(allow sysctl-read (sysctl-name \"security.mac.lockdown_mode_state\"))"
        "(allow sysctl-read (sysctl-name \"kern.bootargs\"))"
        "(allow file-read* (subpath \"%s\") (subpath \"/usr/lib\")"
        " (subpath \"/System/Library\") (literal \"%s\") (literal \"%s\") (subpath \"%s\"))"
        "(allow process-exec (literal \"%s\"))",
        runtime, worker, probe, app, interpreter);
    if (n < 0 || (size_t)n >= sizeof(profile)) fail();
    int sandbox_rc = -99;
    if (combined) {
        void *library = dlopen("/usr/lib/libsandbox.dylib", RTLD_NOW | RTLD_LOCAL);
        if (!library) fail();
        sandbox_init_fn apply = (sandbox_init_fn)dlsym(library, "sandbox_init");
        if (!apply) fail();
        struct rlimit zero = {0, 0};
        if (setrlimit(RLIMIT_NPROC, &zero)) fail();
        char *error = NULL;
        sandbox_rc = apply(profile, 0, &error);
        if (sandbox_rc) fail();
    }
    struct rlimit limit;
    if (getrlimit(RLIMIT_NPROC, &limit) ||
        (combined && (limit.rlim_cur || limit.rlim_max)) || now() >= original) fail();
    char report[256];
    n = snprintf(report, sizeof(report),
        "{\"kind\":\"d01-preexec\",\"pid\":%d,\"sandbox_rc\":%d,"
        "\"nproc\":[%llu,%llu]}\n", getpid(), sandbox_rc,
        (unsigned long long)limit.rlim_cur, (unsigned long long)limit.rlim_max);
    if (n < 0 || (size_t)n >= sizeof(report) || write(1, report, n) != n) fail();
    /* The policy is already installed; same PID replaces only its image.
       IMPORTANT: the exact-interpreter allow rule may also permit re-exec.
       CI must report that escape; this launcher does not claim one-shot exec. */
    execv(interpreter, &argv[4]);
    fail();
}
#else
#error D01-A pre-exec prototype requires macOS
#endif
