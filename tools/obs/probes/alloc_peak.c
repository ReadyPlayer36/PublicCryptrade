// alloc_peak.c - LD_PRELOAD peak allocator for Appendix A.5 (V17-04; direct-mmap fence V18-03; concurrency and
// range-awareness v2.0, V19-01/V19-02).
//
// TWO counters, because one allocator family is not the whole story:
//
//   1. MALLOC FAMILY (malloc/calloc/realloc/free): live bytes across every malloc arena and thread, atomically, with
//      the PEAK delta since the last reset. This is what mallinfo2 cannot give: a difference of two samples misses
//      allocations that live and die between them, mallinfo2 sees only the calling thread's arena(s), and uordblks
//      alone excludes mmapped blocks.
//
//   2. DIRECT mmap (mmap/mmap64/munmap/mremap, MAP_ANONYMOUS|MAP_PRIVATE only): live mapped bytes and their peak since
//      the last reset. Python's own object allocator does NOT go through malloc for its 1 MiB arenas, so a malloc-only
//      interposer is blind to them (A.5.7). Blocks that malloc itself serves with mmap are NOT double counted here:
//      glibc calls __mmap internally, not the interposable symbol, and they are already counted by malloc_usable_size.
//
// CONCURRENCY (V19-01). The measured region contains a ThreadingHTTPServer and worker threads, so the mmap channel is a
// multi-writer structure. Every mutation of the range table and of every live total happens under one spinlock
// (map_flag), and the live totals are updated with a true atomic read-modify-write (fetch_add / a CAS-decrement loop),
// never a load-then-store pair. The peak is published with a compare-exchange loop on the current live value, so no
// observation is lost when several threads cross the high-water mark at once.
//
// RANGE AWARENESS (V19-02). The table stores [start, start+len) ranges, not bare lengths, so
//   * munmap of a PARTIAL range subtracts exactly the overlap and keeps (or splits into) the surviving pieces;
//   * mremap is accounted as remove(old) + add(new), including MREMAP_FIXED (which unmaps its target first) and
//     MREMAP_DONTUNMAP (which keeps the source);
//   * an mmap that lands on MAP_FIXED over an existing tracked range subtracts the replaced bytes before adding the new
//     ones, and ADJACENT ranges are coalesced so a page-by-page workload cannot exhaust the table.
//
// FAIL CLOSED (V19-01). If the table cannot hold a range, the shim writes a diagnostic and calls abort(). It never
// silently drops an entry: a dropped entry would make map_peak an under-count, and an under-count is exactly the
// failure mode this instrument exists to prevent. ALLOC_PEAK_MAP_SLOTS may only REDUCE the capacity (test use: it is how
// probe8 proves the abort path); production runs use the compiled default.
//
// REALLOC FAILURE (V19 follow-up). `realloc(p, n)` with n != 0 that returns NULL leaves p valid and owned by the caller,
// so the shim returns NULL and moves NOTHING: subtracting usable(p) there would erase a live block from the total and
// every later sample would be an under-count. `realloc(p, 0)` is different - glibc frees p and returns NULL - and is
// accounted as a free.
//
// Public symbols:
//   void   alloc_peak_reset(void):        baseline := live, peak := 0, and the same for the mmap counter
//   size_t alloc_peak_peak(void):         peak live-minus-baseline malloc bytes since the reset
//   size_t alloc_peak_map_peak(void):     peak live anonymous-private mmap bytes since the reset (A.5.7)
//   size_t alloc_peak_map_live(void):     current live mapped bytes (diagnostic; probe8 asserts on it)
//   size_t alloc_peak_map_regions(void):  current tracked ranges (diagnostic; coalescing must keep this flat)
//   size_t alloc_peak_map_capacity(void): the effective table capacity (diagnostic)
//
// On exit it also writes {"peak":N,"map_peak":M,"map_live":L,"map_regions":R} to $ALLOC_PEAK_FILE when set.
//
// Build: cc -shared -fPIC -O2 -Wall -Wextra -o alloc_peak.so alloc_peak.c
//
// FENCED LIMITS (A.5.4/A.5.7 - stated, not hidden):
//   * not intercepted: posix_memalign/aligned_alloc/memalign/valloc/pvalloc (glibc serves them through malloc on the
//     measured paths, but a direct call would be invisible), brk/sbrk, alloca, thread stacks, static/BSS, and any
//     library that calls its own private allocator;
//   * file-backed and shared mappings are excluded on purpose (page cache is out of Domain B, A.5.6);
//   * a range the shim did not create (a mapping that predates LD_PRELOAD) is not in the table, so unmapping it subtracts
//     nothing - it was never counted either.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <malloc.h>
#include <sched.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

/* glibc's own allocator entry points: the bootstrap fallback, so that symbol resolution can never recurse. */
extern void *__libc_malloc(size_t);
extern void *__libc_calloc(size_t, size_t);
extern void *__libc_realloc(void *, size_t);
extern void  __libc_free(void *);

static void *(*real_malloc)(size_t);
static void *(*real_calloc)(size_t, size_t);
static void *(*real_realloc)(void *, size_t);
static void  (*real_free)(void *);

/* Resolve the real symbols ONCE, in a constructor: after this point the wrappers never call dlsym, so they are safe on
   any thread. If the constructor's dlsym is itself still resolving (it allocates), the __libc_* fallbacks below serve
   the call instead of recursing. */
__attribute__((constructor)) static void alloc_peak_bootstrap(void) {
    real_malloc = (void *(*)(size_t))dlsym(RTLD_NEXT, "malloc");
    real_calloc = (void *(*)(size_t, size_t))dlsym(RTLD_NEXT, "calloc");
    real_realloc = (void *(*)(void *, size_t))dlsym(RTLD_NEXT, "realloc");
    real_free = (void (*)(void *))dlsym(RTLD_NEXT, "free");
}

static size_t usable(void *p) { return p ? malloc_usable_size(p) : 0; }

/* ---- malloc channel ------------------------------------------------------------------------------------------- */

static _Atomic size_t live = 0;
static _Atomic size_t base = 0;
static _Atomic size_t peak = 0;

static void observe_peak(_Atomic size_t *baseline, size_t now, _Atomic size_t *high_water) {
    size_t b = atomic_load_explicit(baseline, memory_order_relaxed);
    size_t rel = now > b ? now - b : 0;
    size_t seen = atomic_load_explicit(high_water, memory_order_relaxed);
    while (rel > seen && !atomic_compare_exchange_weak_explicit(high_water, &seen, rel,
                                                               memory_order_relaxed, memory_order_relaxed)) { }
}

static void track_add(size_t n) {
    size_t now = atomic_fetch_add_explicit(&live, n, memory_order_relaxed) + n;
    observe_peak(&base, now, &peak);
}

static void track_sub(size_t n) {
    size_t cur = atomic_load_explicit(&live, memory_order_relaxed);
    for (;;) {
        size_t next = cur > n ? cur - n : 0;
        if (atomic_compare_exchange_weak_explicit(&live, &cur, next, memory_order_relaxed, memory_order_relaxed)) {
            return;
        }
    }
}

/* ---- direct anonymous-private mappings (A.5.7), lock and range table (V19-01/V19-02) --------------------------- */

#define MAP_SLOTS_DEFAULT 1024
#define MAP_SLOTS_MAX 4096

typedef struct { uintptr_t start; size_t len; } range;

static _Atomic size_t map_live = 0;
static _Atomic size_t map_base = 0;
static _Atomic size_t map_peak = 0;
static _Atomic unsigned map_flag = 0;                 /* 0 = free, 1 = held */
static range map_tab[MAP_SLOTS_MAX];
static size_t map_used = 0;
static size_t map_cap = 0;
static _Atomic size_t map_regions_high = 0;

static void map_lock(void) {
    while (atomic_exchange_explicit(&map_flag, 1u, memory_order_acquire)) {
        while (atomic_load_explicit(&map_flag, memory_order_relaxed)) sched_yield();
    }
}

static void map_unlock(void) { atomic_store_explicit(&map_flag, 0u, memory_order_release); }

static void map_capacity(void) {                      /* called with the lock held */
    if (map_cap) return;
    size_t cap = MAP_SLOTS_DEFAULT;
    const char *env = getenv("ALLOC_PEAK_MAP_SLOTS");        /* TEST-ONLY: can only reduce the capacity */
    if (env && *env) {
        char *end = NULL;
        errno = 0;
        unsigned long v = strtoul(env, &end, 10);
        if (errno == 0 && end && *end == '\0' && v >= 1 && v <= MAP_SLOTS_MAX) cap = (size_t)v;
    }
    map_cap = cap;
}

static void map_fail_closed(const char *why) {        /* called with the lock held; never returns */
    char buf[256];
    int n = snprintf(buf, sizeof buf,
                     "alloc_peak: FATAL: %s (tracked %zu, capacity %zu, live %zu): refusing to under-report\n",
                     why, map_used, map_cap ? map_cap : (size_t)MAP_SLOTS_DEFAULT,
                     (size_t)atomic_load_explicit(&map_live, memory_order_relaxed));
    if (n > 0) {
        ssize_t written = write(STDERR_FILENO, buf, (size_t)(n < (int)sizeof buf ? n : (int)sizeof buf));
        (void)written;
    }
    abort();
}

static void map_reserve(size_t extra) {
    if (map_cap == 0) map_capacity();
    if (map_used + extra <= map_cap) return;
    map_fail_closed("range table capacity exhausted");
}

static void map_publish_peak(void) {
    size_t b = atomic_load_explicit(&map_base, memory_order_relaxed);
    size_t now = atomic_load_explicit(&map_live, memory_order_relaxed);
    size_t rel = now > b ? now - b : 0;
    size_t seen = atomic_load_explicit(&map_peak, memory_order_relaxed);
    while (rel > seen && !atomic_compare_exchange_weak_explicit(&map_peak, &seen, rel,
                                                               memory_order_relaxed, memory_order_relaxed)) { }
}

static void map_live_add(size_t n) {
    atomic_fetch_add_explicit(&map_live, n, memory_order_relaxed);
}

static void map_live_sub(size_t n) {
    size_t cur = atomic_load_explicit(&map_live, memory_order_relaxed);
    for (;;) {
        size_t next = cur > n ? cur - n : 0;
        if (atomic_compare_exchange_weak_explicit(&map_live, &cur, next, memory_order_relaxed, memory_order_relaxed)) {
            return;
        }
    }
}

/* Subtract [s, e) from the tracked set, adjusting the live total by exactly the overlap. Returns bytes removed. */
static size_t map_forget(uintptr_t s, uintptr_t e) {  /* called with the lock held */
    size_t removed = 0;
    size_t i = 0;
    while (i < map_used) {
        uintptr_t rs = map_tab[i].start;
        uintptr_t re = rs + map_tab[i].len;
        if (e <= rs || s >= re) { i++; continue; }
        uintptr_t lo = s > rs ? s : rs;
        uintptr_t hi = e < re ? e : re;
        removed += (size_t)(hi - lo);
        if (s <= rs && e >= re) {                              /* fully covered: drop the entry */
            map_tab[i] = map_tab[--map_used];
            continue;
        }
        if (s <= rs) {                                         /* head removed */
            map_tab[i].start = e;
            map_tab[i].len = (size_t)(re - e);
            i++;
            continue;
        }
        if (e >= re) {                                         /* tail removed */
            map_tab[i].len = (size_t)(s - rs);
            i++;
            continue;
        }
        map_reserve(1);                                        /* hole punched: split in two */
        map_tab[i].len = (size_t)(s - rs);
        map_tab[map_used].start = e;
        map_tab[map_used].len = (size_t)(re - e);
        map_used++;
        i++;
    }
    if (removed) map_live_sub(removed);
    return removed;
}

static size_t map_len_at(uintptr_t s) {                /* called with the lock held */
    for (size_t i = 0; i < map_used; i++) {
        if (map_tab[i].start == s) return map_tab[i].len;
    }
    return 0;
}

/* Add the new mapping [s, s+len): drop whatever it replaced, then coalesce adjacent ranges (bookkeeping only). */
static void map_record(uintptr_t s, size_t len) {      /* called with the lock held */
    if (len == 0) return;
    uintptr_t e = s + len;
    (void)map_forget(s, e);                            /* MAP_FIXED installs over the old bytes */
    size_t i = 0;
    while (i < map_used) {
        uintptr_t rs = map_tab[i].start;
        uintptr_t re = rs + map_tab[i].len;
        if (re < s || rs > e) { i++; continue; }
        if (rs < s) s = rs;
        if (re > e) e = re;
        map_tab[i] = map_tab[--map_used];
    }
    map_reserve(1);                                    /* before the total moves: a refused range must not be counted */
    map_live_add(len);                                 /* the NEW bytes, not the coalesced extent */
    map_tab[map_used].start = s;
    map_tab[map_used].len = (size_t)(e - s);
    map_used++;
    if (map_used > atomic_load_explicit(&map_regions_high, memory_order_relaxed)) {
        atomic_store_explicit(&map_regions_high, map_used, memory_order_relaxed);
    }
    map_publish_peak();
}

/* ---- public API ------------------------------------------------------------------------------------------------ */

void alloc_peak_reset(void) {
    atomic_store_explicit(&base, atomic_load_explicit(&live, memory_order_relaxed), memory_order_relaxed);
    atomic_store_explicit(&peak, 0, memory_order_relaxed);
    map_lock();
    atomic_store_explicit(&map_base, atomic_load_explicit(&map_live, memory_order_relaxed), memory_order_relaxed);
    atomic_store_explicit(&map_peak, 0, memory_order_relaxed);
    map_unlock();
}

size_t alloc_peak_peak(void) { return atomic_load_explicit(&peak, memory_order_relaxed); }

size_t alloc_peak_map_peak(void) { return atomic_load_explicit(&map_peak, memory_order_relaxed); }

size_t alloc_peak_map_live(void) { return atomic_load_explicit(&map_live, memory_order_relaxed); }

size_t alloc_peak_map_regions(void) {
    map_lock();
    size_t n = map_used;
    map_unlock();
    return n;
}

size_t alloc_peak_map_capacity(void) {
    map_lock();
    if (map_cap == 0) map_capacity();
    size_t n = map_cap;
    map_unlock();
    return n;
}

/* ---- malloc family --------------------------------------------------------------------------------------------- */

void *malloc(size_t size) {
    void *p = real_malloc ? real_malloc(size) : __libc_malloc(size);
    track_add(usable(p));
    return p;
}

void free(void *p) {
    size_t was = usable(p);
    if (was) track_sub(was);
    if (real_free) real_free(p); else __libc_free(p);
}

void *calloc(size_t n, size_t size) {
    void *p = real_calloc ? real_calloc(n, size) : __libc_calloc(n, size);
    track_add(usable(p));
    return p;
}

/* realloc(p, n) with n != 0 either returns a NEW block (p is gone) or fails and leaves p intact. On failure the
   original allocation is still live and still counted, so the tracking state must not move at all: usable(NULL) is 0,
   and subtracting the old size there would erase a block that the caller still owns - an under-count, which is the
   one error this instrument must never make. realloc(p, 0) is the other case: glibc frees p and returns NULL, so the
   subtraction IS correct and is kept below. */
void *realloc(void *old, size_t size) {
    size_t was = usable(old);
    void *p = real_realloc ? real_realloc(old, size) : __libc_realloc(old, size);
    if (p == NULL && size != 0) return NULL;             /* failure: old block untouched, tracking untouched too */
    size_t now = usable(p);
    if (now >= was) track_add(now - was); else track_sub(was - now);
    return p;
}

/* ---- direct mmap family ---------------------------------------------------------------------------------------- */

#if defined(SYS_mmap) && defined(SYS_munmap)
void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    void *p = (void *)syscall(SYS_mmap, addr, len, prot, flags, fd, off);
    if (p == MAP_FAILED) return p;
    if ((flags & MAP_ANONYMOUS) && (flags & MAP_PRIVATE) && !(flags & MAP_SHARED)) {
        map_lock();
        map_record((uintptr_t)p, len);
        map_unlock();
    }
    return p;
}

void *mmap64(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    return mmap(addr, len, prot, flags, fd, off);
}

int munmap(void *addr, size_t len) {
    int rc = (int)syscall(SYS_munmap, addr, len);
    if (rc == 0 && len) {
        map_lock();
        (void)map_forget((uintptr_t)addr, (uintptr_t)addr + len);
        map_unlock();
    }
    return rc;
}

#if defined(SYS_mremap)
void *mremap(void *old, size_t old_len, size_t new_len, int flags, ...) {
    void *target = NULL;
    if (flags & MREMAP_FIXED) {
        va_list ap;
        va_start(ap, flags);
        target = va_arg(ap, void *);
        va_end(ap);
    }
    void *p = (void *)syscall(SYS_mremap, old, old_len, new_len, flags, target);
    if (p == MAP_FAILED) return p;
    size_t source = old_len;
    map_lock();
    if (source == 0) source = map_len_at((uintptr_t)old);   /* old_len 0 means "size not stated" */
    if (flags & MREMAP_DONTUNMAP) {                         /* the source mapping survives */
        if (source) map_record((uintptr_t)p, new_len);
    } else {
        size_t removed = source ? map_forget((uintptr_t)old, (uintptr_t)old + source) : 0;
        if (removed) map_record((uintptr_t)p, new_len);      /* untracked source: do not start counting it */
    }
    map_unlock();
    return p;
}
#endif
#endif

__attribute__((destructor)) static void report(void) {
    const char *path = getenv("ALLOC_PEAK_FILE");
    if (!path || !*path) return;
    map_lock();
    size_t map_now = atomic_load_explicit(&map_peak, memory_order_relaxed);
    size_t map_still = atomic_load_explicit(&map_live, memory_order_relaxed);
    size_t regions = map_used;
    map_unlock();
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "{\"peak\":%zu,\"map_peak\":%zu,\"map_live\":%zu,\"map_regions\":%zu}\n",
            atomic_load_explicit(&peak, memory_order_relaxed), map_now, map_still, regions);
    fclose(f);
}
