// alloc_peak.c - LD_PRELOAD peak allocator for Appendix A.5 (V17-04; direct-mmap fence added by V18-03).
//
// TWO counters, because one allocator family is not the whole story:
//
//   1. MALLOC FAMILY (malloc/calloc/realloc/free): live bytes across every malloc arena and thread, atomically, with
//      the PEAK delta since the last reset. This is what mallinfo2 cannot give: a difference of two samples misses
//      allocations that live and die between them, mallinfo2 sees only the calling thread's arena(s), and uordblks
//      alone excludes mmapped blocks.
//
//   2. DIRECT mmap (mmap/mmap64/munmap, MAP_ANONYMOUS|MAP_PRIVATE only): live mapped bytes and their peak since the
//      last reset. Python's own object allocator does NOT go through malloc for its 1 MiB arenas, so a malloc-only
//      interposer is blind to them (A.5.7). Blocks that malloc itself serves with mmap are NOT double counted here:
//      glibc calls __mmap internally, not the interposable symbol, and they are already counted by malloc_usable_size.
//
// Public symbols:
//   void   alloc_peak_reset(void):    baseline := live, peak := 0, and the same for the mmap counter
//   size_t alloc_peak_peak(void):     peak live-minus-baseline malloc bytes since the reset
//   size_t alloc_peak_map_peak(void): peak live anonymous-private mmap bytes since the reset (A.5.7)
//
// On exit it also writes {"peak":N,"map_peak":M} to $ALLOC_PEAK_FILE when set (fallback for processes that cannot
// call the getters).
//
// Build: cc -shared -fPIC -O2 -o alloc_peak.so alloc_peak.c
//
// FENCED LIMITS (A.5.4/A.5.7 - stated, not hidden):
//   * not intercepted: posix_memalign/aligned_alloc/memalign/valloc/pvalloc (glibc serves them through malloc on the
//     measured paths, but a direct call would be invisible), brk/sbrk, alloca, thread stacks, static/BSS, and any
//     library that calls its own private allocator;
//   * file-backed and shared mappings are excluded on purpose (page cache is out of Domain B, A.5.6);
//   * the mmap table is a single-writer structure: concurrent mappers are counted in the totals, but a munmap racing
//     the snapshot may leave one entry stale. The measured regions are single-threaded (A.5.7).
#define _GNU_SOURCE
#include <dlfcn.h>
#include <malloc.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

static _Atomic size_t live = 0;
static _Atomic size_t base = 0;
static _Atomic size_t peak = 0;
static void *(*real_malloc)(size_t);
static void  (*real_free)(void *);
static void *(*real_calloc)(size_t, size_t);
static void *(*real_realloc)(void *, size_t);

static size_t usable(void *p) { return p ? malloc_usable_size(p) : 0; }

static void observe_peak(_Atomic size_t *baseline, size_t now, _Atomic size_t *high_water) {
    size_t b = atomic_load(baseline);
    size_t rel = now > b ? now - b : 0;
    size_t seen = atomic_load(high_water);
    while (rel > seen && !atomic_compare_exchange_weak(high_water, &seen, rel)) { }
}

static void track(long delta) {
    size_t now = delta >= 0 ? atomic_fetch_add(&live, (size_t)delta) + (size_t)delta
                            : atomic_fetch_sub(&live, (size_t)-delta) - (size_t)-delta;
    observe_peak(&base, now, &peak);
}

/* ---- direct anonymous-private mappings (A.5.7) ---------------------------------------------------------------- */

#define MAP_SLOTS 512
static _Atomic size_t map_state[3];          /* 0: live, 1: baseline, 2: peak */
static struct { void *addr; size_t len; } map_tab[MAP_SLOTS];
static size_t map_used = 0;

static void map_tracked(void *addr, size_t len) {
    size_t now = atomic_fetch_add(&map_state[0], len) + len;
    if (map_used < MAP_SLOTS) {
        map_tab[map_used].addr = addr;
        map_tab[map_used].len = len;
        map_used += 1;
    }
    observe_peak(&map_state[1], now, &map_state[2]);
}

static void map_untracked(void *addr, size_t len) {
    for (size_t i = 0; i < map_used; i++) {
        if (map_tab[i].addr != addr) continue;
        size_t held = map_tab[i].len;
        size_t drop = len < held ? len : held;
        size_t now = atomic_load(&map_state[0]);
        atomic_store(&map_state[0], now > drop ? now - drop : 0);
        map_used -= 1;
        map_tab[i] = map_tab[map_used];
        return;
    }
}

void alloc_peak_reset(void) {
    atomic_store(&base, atomic_load(&live));
    atomic_store(&peak, 0);
    atomic_store(&map_state[1], atomic_load(&map_state[0]));
    atomic_store(&map_state[2], 0);
}

size_t alloc_peak_peak(void) { return atomic_load(&peak); }

size_t alloc_peak_map_peak(void) { return atomic_load(&map_state[2]); }

/* ---- malloc family --------------------------------------------------------------------------------------------- */

void *malloc(size_t size) {
    if (!real_malloc) real_malloc = dlsym(RTLD_NEXT, "malloc");
    void *p = real_malloc(size);
    track((long)usable(p));
    return p;
}

void free(void *p) {
    if (!real_free) real_free = dlsym(RTLD_NEXT, "free");
    long was = (long)usable(p);
    track(-was);
    real_free(p);
}

void *calloc(size_t n, size_t size) {
    if (!real_calloc) real_calloc = dlsym(RTLD_NEXT, "calloc");
    void *p = real_calloc(n, size);
    track((long)usable(p));
    return p;
}

void *realloc(void *old, size_t size) {
    if (!real_realloc) real_realloc = dlsym(RTLD_NEXT, "realloc");
    long was = (long)usable(old);
    void *p = real_realloc(old, size);
    track((long)usable(p) - was);
    return p;
}

/* ---- direct mmap family ---------------------------------------------------------------------------------------- */

#if defined(SYS_mmap) && defined(SYS_munmap)
void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    void *p = (void *)syscall(SYS_mmap, addr, len, prot, flags, fd, off);
    if (p != MAP_FAILED && (flags & MAP_ANONYMOUS) && (flags & MAP_PRIVATE)) map_tracked(p, len);
    return p;
}

void *mmap64(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    return mmap(addr, len, prot, flags, fd, off);
}

int munmap(void *addr, size_t len) {
    int rc = (int)syscall(SYS_munmap, addr, len);
    if (rc == 0) map_untracked(addr, len);
    return rc;
}
#endif

__attribute__((destructor)) static void report(void) {
    const char *path = getenv("ALLOC_PEAK_FILE");
    if (!path || !*path) return;
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "{\"peak\":%zu,\"map_peak\":%zu}\n", atomic_load(&peak), atomic_load(&map_state[2]));
    fclose(f);
}
