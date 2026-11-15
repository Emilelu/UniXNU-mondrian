/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline host fixture only. No generator, physical mapping, PAS or device I/O.
 * argv[1] is the captured firmware directory (normally
 * /mnt/e/k60-work/firmware/adsp). All existing bNN files are included verbatim.
 * The K60A and FAT carriers below are constructed only in process memory. */
#include <errno.h>
#include <limits.h>
#include "test-k60-owner-fixture.h"
#include "../../drivers/PongPower/K60AdspImageReader.h"

#ifdef K60_ADSP_TEST_LINKED
/* Tiny valid linked carrier; production test remains completely in-memory. */
const uint8_t k60_adsp_blob[] = {
    'K','6','0','A', 1,0,0,0,
    8,0, 3,0,0,0, 32,0,0,0,
    'a','d','s','p','.','m','d','t',
    0,0,0,0,0,0, 0xaa,0xbb,0xcc, 0,0,0,0,0
};
const uint64_t k60_adsp_blob_len = sizeof k60_adsp_blob;
#endif

#define IMAGE_BASE UINT64_C(0x9fd00000)
#define IMAGE_SPAN 0x3100000u
#define META_BYTES 5404u
#define GUARD 32u
#define SENTINEL 0xccu

typedef struct { char name[9]; uint8_t *data; size_t bytes; } Part;
typedef struct { uint8_t *data; size_t bytes; } Carrier;
typedef struct { Part part[K60_ADSP_BLOB_MAX_ENTRIES]; unsigned count; Carrier blob; } Capture;
static Capture captured;
static unsigned scenarios;

static void scenario(const char *name) { fx_name = name; ++scenarios; }
static size_t align8(size_t n) { CHECK(n <= SIZE_MAX - 7); return (n + 7u) & ~(size_t)7; }
static int filled(const void *p, size_t n, uint8_t v)
{ const uint8_t *b = p; while (n--) if (*b++ != v) return 0; return 1; }
static void *allocate(size_t n) { void *p = malloc(n); CHECK(p != NULL); return p; }

static Carrier make_blob(const Part *parts, unsigned count)
{
    CHECK(count && count <= K60_ADSP_BLOB_MAX_ENTRIES);
    size_t names = 8u + (size_t)count * 10u, at = names + (size_t)count * 8u;
    size_t bytes = align8(at);
    for (unsigned i = 0; i < count; ++i) {
        CHECK(strlen(parts[i].name) == 8 && parts[i].bytes && parts[i].bytes <= UINT32_MAX);
        CHECK(parts[i].bytes <= UINT32_MAX - bytes);
        bytes = align8(bytes + parts[i].bytes);
    }
    CHECK(bytes <= UINT32_MAX);
    Carrier b = {allocate(bytes), bytes}; memset(b.data, 0, bytes);
    memcpy(b.data, "K60A", 4); fx_le32(b.data + 4, count);
    size_t body = align8(at);
    for (unsigned i = 0; i < count; ++i) {
        uint8_t *entry = b.data + 8u + (size_t)i * 10u;
        fx_le16(entry, 8); fx_le32(entry + 2, (uint32_t)parts[i].bytes);
        fx_le32(entry + 6, (uint32_t)body);
        memcpy(b.data + names + (size_t)i * 8u, parts[i].name, 8);
        memcpy(b.data + body, parts[i].data, parts[i].bytes);
        body = align8(body + parts[i].bytes);
    }
    CHECK(body == bytes); return b;
}
static int load_part(Part *part, const char *dir, const char *name, int optional)
{
    char path[4096]; int n = snprintf(path, sizeof path, "%s/%s", dir, name);
    CHECK(n > 0 && (size_t)n < sizeof path);
    errno = 0; FILE *file = fopen(path, "rb");
    if (!file && optional && errno == ENOENT) return 0;
    if (!file) fprintf(stderr, "cannot read captured input %s: %s\n", path, strerror(errno));
    CHECK(file != NULL); CHECK(!fseek(file, 0, SEEK_END)); long length = ftell(file);
    CHECK(length > 0 && (uint64_t)length <= UINT32_MAX); CHECK(!fseek(file, 0, SEEK_SET));
    part->bytes = (size_t)length; part->data = allocate(part->bytes);
    CHECK(fread(part->data, 1, part->bytes, file) == part->bytes); CHECK(!ferror(file));
    CHECK(!fclose(file)); memcpy(part->name, name, 9); return 1;
}
static const Part *find_part(const char *name)
{
    for (unsigned i = 0; i < captured.count; ++i)
        if (!strcmp(captured.part[i].name, name)) return &captured.part[i];
    return NULL;
}
static void load_capture(const char *dir)
{
    scenario("capture all existing bNN without synthesizing b24");
    CHECK(load_part(&captured.part[captured.count++], dir, "adsp.mdt", 0));
    for (unsigned i = 0; i < 100; ++i) {
        char name[9] = "adsp.b00"; name[6] = (char)('0' + i / 10); name[7] = (char)('0' + i % 10);
        CHECK(captured.count < K60_ADSP_BLOB_MAX_ENTRIES);
        if (load_part(&captured.part[captured.count], dir, name, 1)) ++captured.count;
    }
    CHECK(captured.count == 26 && !find_part("adsp.b24"));
    CHECK(find_part("adsp.mdt")->bytes == META_BYTES);
    captured.blob = make_blob(captured.part, captured.count);
}
static void unchanged_error(K60AdspReader *r, const char *part, uint32_t bytes, int error)
{
    uint8_t dst[1024], before[1024]; CHECK(bytes <= sizeof dst);
    memset(dst, 0xa6, sizeof dst); memcpy(before, dst, sizeof before);
    CHECK(k60_adsp_reader_read(r, part, dst, bytes) == error);
    CHECK(!memcmp(dst, before, sizeof dst));
    const uint8_t *out = before; size_t n = 0x13579u;
    if (error != K60AdspReaderReadFailed) {
        CHECK(k60_adsp_reader_borrow(r, part, &out, &n) == error);
        CHECK(out == before && n == 0x13579u);
    }
}
static void invalid_blob(uint8_t *bytes, size_t n)
{
    K60AdspReader r = {0}, before; r.bytes = 17; before = r;
    CHECK(k60_adsp_reader_blob(&r, bytes, n) == -7); CHECK(!memcmp(&r, &before, sizeof r));
    /* Revalidate at access time too: malformed live backing cannot copy or borrow. */
    K60AdspReader live = {0}; live.base = bytes; live.bytes = n; live.mode = 1;
    unchanged_error(&live, "adsp.mdt", 3, -7);
}
static void blob_tests(void)
{
    static uint8_t a[] = {0x11, 0x22, 0x33}, b[] = {1,2,3,4,5,6,7,8,9}, c[] = {0x44};
    Part p[] = {{"adsp.mdt",a,sizeof a},{"adsp.b10",b,sizeof b},{"adsp.b25",c,sizeof c}};
    Carrier good = make_blob(p, 3); uint8_t *bad = allocate(good.bytes + 8);
    scenario("K60A aliases, exact size and no-write errors");
    K60AdspReader r = {0}, empty = {0}; CHECK(!k60_adsp_reader_blob(&r, good.data, good.bytes));
    for (unsigned i = 0; i < 3; ++i) {
        const char *name = i == 0 ? "mdt" : i == 1 ? "adsp" : "adsp.mdt";
        uint8_t out[5] = {0xa5,0xa5,0xa5,0xa5,0xa5}; const uint8_t *borrow = NULL; size_t n = 0;
        CHECK(!k60_adsp_reader_read(&r, name, out + 1, 3));
        CHECK(out[0] == 0xa5 && out[4] == 0xa5 && !memcmp(out + 1, a, 3));
        CHECK(!k60_adsp_reader_borrow(&r, name, &borrow, &n)); CHECK(n == 3 && !memcmp(borrow, a, n));
    }
    unchanged_error(&r, "adsp.mdt", 2, -5); unchanged_error(&r, "mdt", 4, -5);
    unchanged_error(&r, "adsp.b24", 3, -6); unchanged_error(&empty, "mdt", 3, -6);
    const char *invalid[] = {"", "b10", "ADSP.MDT", "adsp.b1", "adsp.b001", "adsp.b-1", "../adsp.mdt", "adsp.mdtX"};
    for (unsigned i = 0; i < sizeof invalid / sizeof *invalid; ++i) unchanged_error(&r, invalid[i], 3, -1);
    unchanged_error(&r, NULL, 3, -1);
    uint8_t dst[8]; memset(dst, 0x77, sizeof dst);
    CHECK(k60_adsp_reader_blob(&empty, NULL, 8) == -6 && !empty.mode);
    CHECK(k60_adsp_reader_blob(&empty, good.data, 0) == -6 && !empty.mode);
    CHECK(k60_adsp_reader_blob(NULL, good.data, good.bytes) == -1);
    K60AdspReader snapshot = r;
    CHECK(k60_adsp_reader_blob(&r, good.data, good.bytes) == -1 && !memcmp(&r, &snapshot, sizeof r));
    CHECK(k60_adsp_reader_read(&r, "mdt", NULL, 3) == -1);
    CHECK(k60_adsp_reader_read(&r, "mdt", good.data, 3) == -1);
    CHECK(k60_adsp_reader_read(&r, "mdt", &r, 3) == -1 && !memcmp(&r, &snapshot, sizeof r));
    size_t n = 0x1234; const uint8_t *out = dst;
    CHECK(k60_adsp_reader_borrow(&r, "mdt", NULL, &n) == -1 && n == 0x1234);
    CHECK(k60_adsp_reader_borrow(&r, "mdt", &out, NULL) == -1 && out == dst);
    union { const uint8_t *p; size_t size; } alias; memset(&alias, 0x66, sizeof alias);
    uint8_t alias_before[sizeof alias]; memcpy(alias_before, &alias, sizeof alias);
    CHECK(k60_adsp_reader_borrow(&r, "mdt", &alias.p, &alias.size) == -1);
    CHECK(!memcmp(&alias, alias_before, sizeof alias));
    CHECK(k60_adsp_reader_borrow(&r, "mdt", (const uint8_t **)(void *)&r, &n) == -1);
    CHECK(!memcmp(&r, &snapshot, sizeof r));
    CHECK(k60_adsp_reader_borrow(&r, "mdt", (const uint8_t **)(void *)good.data, &n) == -1);
    CHECK(filled(dst, sizeof dst, 0x77));

    scenario("K60A rejects every truncation and trailing bytes");
    for (size_t i = 1; i < good.bytes; ++i) invalid_blob(good.data, i);
    memcpy(bad, good.data, good.bytes); memset(bad + good.bytes, 0, 8); invalid_blob(bad, good.bytes + 8);
    scenario("K60A malformed magic/count/names/dupes/size/padding/offset/overflow");
#define BAD_BLOB(change) do { memcpy(bad, good.data, good.bytes); change; invalid_blob(bad, good.bytes); } while (0)
    BAD_BLOB(bad[0] = 'X'); BAD_BLOB(fx_le32(bad + 4, 0));
    BAD_BLOB(fx_le32(bad + 4, 65)); BAD_BLOB(fx_le32(bad + 4, UINT32_MAX));
    BAD_BLOB(fx_le16(bad + 8, 0)); BAD_BLOB(fx_le16(bad + 8, 7));
    BAD_BLOB(fx_le16(bad + 8, UINT16_MAX)); BAD_BLOB(bad[38] = 'A');
    BAD_BLOB(bad[38 + 5] = '/'); BAD_BLOB(bad[38 + 6] = 0);
    BAD_BLOB(memcpy(bad + 46, bad + 38, 8));
    BAD_BLOB(fx_le32(bad + 10, 0)); BAD_BLOB(fx_le32(bad + 10, UINT32_MAX));
    BAD_BLOB(bad[62] = 1); BAD_BLOB(bad[67] = 1); BAD_BLOB(bad[good.bytes - 1] = 1);
    BAD_BLOB(fx_le32(bad + 14, 63)); BAD_BLOB(fx_le32(bad + 14, 0));
    BAD_BLOB(fx_le32(bad + 14, 72)); BAD_BLOB(fx_le32(bad + 24, 64));
    BAD_BLOB(fx_le32(bad + 24, 80)); BAD_BLOB(fx_le32(bad + 14, UINT32_MAX - 7u));
#undef BAD_BLOB
#if SIZE_MAX > UINT32_MAX
    CHECK(k60_adsp_reader_blob(&empty, good.data, (size_t)UINT32_MAX + 1u) == -7 && !empty.mode);
#endif
#ifdef K60_ADSP_TEST_LINKED
    scenario("linked K60A carrier initializes and reads exact bytes");
    K60AdspReader linked = {0}; memset(dst, 0x77, sizeof dst);
    CHECK(!k60_adsp_reader_linked(&linked) && linked.mode);
    CHECK(!k60_adsp_reader_read(&linked, "mdt", dst + 1, 3));
    CHECK(dst[0] == 0x77 && dst[4] == 0x77 && dst[1] == 0xaa && dst[2] == 0xbb && dst[3] == 0xcc);
    memset(dst, 0x77, sizeof dst); CHECK(!k60_adsp_read("adsp", dst + 1, 3));
    CHECK(dst[0] == 0x77 && dst[4] == 0x77 && dst[1] == 0xaa && dst[2] == 0xbb && dst[3] == 0xcc);
#else
    scenario("linked weak carrier absent remains -6 and cannot touch output");
    CHECK(k60_adsp_reader_linked(&empty) == -6 && !empty.mode);
    CHECK(k60_adsp_read("mdt", dst, 3) == -6 && filled(dst, sizeof dst, 0x77));
#endif
    free(bad); free(good.data);
}

#define FAT_BYTES (64u * 512u)
#define FAT_ROOT 1024u
#define FAT_DIR 1536u
#define FAT_FILE 2048u
static void fat_entry(uint8_t *image, unsigned cluster, uint32_t value)
{ fx_le32(image + 512u + cluster * 4u, value); }
static void directory_entry(uint8_t *e, const char name[11], uint8_t attrs, uint32_t cluster, uint32_t bytes)
{
    memcpy(e, name, 11); e[11] = attrs; fx_le16(e + 20, (uint16_t)(cluster >> 16));
    fx_le16(e + 26, (uint16_t)cluster); fx_le32(e + 28, bytes);
}
static void make_fat(uint8_t *image)
{
    memset(image, 0, FAT_BYTES); image[510] = 0x55; image[511] = 0xaa;
    fx_le16(image + 11, 512); image[13] = 1; fx_le16(image + 14, 1); image[16] = 1;
    fx_le32(image + 32, 64); fx_le32(image + 36, 1); fx_le32(image + 44, 2);
    fat_entry(image, 0, 0x0ffffff8); fat_entry(image, 1, 0x0fffffff);
    fat_entry(image, 2, 0x0fffffff); fat_entry(image, 3, 0x0fffffff);
    fat_entry(image, 4, 5); fat_entry(image, 5, 0x0fffffff); fat_entry(image, 6, 0x0fffffff);
    directory_entry(image + FAT_ROOT, "ADSP       ", 16, 3, 0);
    directory_entry(image + FAT_DIR, "ADSP    MDT", 32, 4, 700);
    directory_entry(image + FAT_DIR + 32, "ADSP    B10", 32, 6, 9);
    for (unsigned i = 0; i < 700; ++i) image[FAT_FILE + i] = (uint8_t)(i * 17u + 3u);
    for (unsigned i = 0; i < 9; ++i) image[3072 + i] = (uint8_t)(0xa0u + i);
}
static void bad_fat(uint8_t *bytes, size_t n)
{
    K60AdspReader r = {0}, before; r.bytes = 11; before = r;
    CHECK(k60_adsp_reader_fat(&r, bytes, n) == -7 && !memcmp(&r, &before, sizeof r));
}
static void fat_tests(void)
{
    uint8_t *good = allocate(FAT_BYTES), *bad = allocate(FAT_BYTES); make_fat(good);
    K60AdspReader r = {0}, empty = {0};
    scenario("explicit mapped FAT contiguous borrowing, aliases and exact reads");
    CHECK(!k60_adsp_reader_fat(&r, good, FAT_BYTES));
    for (unsigned i = 0; i < 3; ++i) {
        const char *name = i == 0 ? "adsp.mdt" : i == 1 ? "mdt" : "adsp";
        uint8_t dst[702]; memset(dst, 0xa5, sizeof dst);
        const uint8_t *p = NULL; size_t n = 0;
        CHECK(!k60_adsp_reader_borrow(&r, name, &p, &n) && p == good + FAT_FILE && n == 700);
        CHECK(!k60_adsp_reader_read(&r, name, dst + 1, 700));
        CHECK(dst[0] == 0xa5 && dst[701] == 0xa5 && !memcmp(dst + 1, p, 700));
    }
    unchanged_error(&r, "mdt", 699, -5); unchanged_error(&r, "mdt", 701, -5);
    unchanged_error(&r, "adsp.b24", 1, -6);
    scenario("FAT stored base and extension cannot alias flattened names");
    memcpy(bad, good, FAT_BYTES); K60AdspReader names = {0};
    CHECK(!k60_adsp_reader_fat(&names, bad, FAT_BYTES));
    memcpy(bad + FAT_DIR, "ADSPMDT    ", 11); unchanged_error(&names, "mdt", 700, -6);
    memcpy(bad + FAT_DIR, "A DSP   MDT", 11); unchanged_error(&names, "mdt", 700, -6);
    memcpy(bad + FAT_DIR, "ADSP    M D", 11); unchanged_error(&names, "mdt", 700, -6);
    memcpy(bad + FAT_DIR + 32, "ADSPB00    ", 11); unchanged_error(&names, "adsp.b00", 9, -6);
    CHECK(k60_adsp_reader_fat(&empty, NULL, FAT_BYTES) == -6 && !empty.mode);
    CHECK(k60_adsp_reader_fat(&empty, good, 0) == -6 && !empty.mode);
    K60AdspReader before = r; CHECK(k60_adsp_reader_fat(&r, good, FAT_BYTES) == -1);
    CHECK(!memcmp(&r, &before, sizeof r));

    scenario("FAT corrupted geometry and truncation fail before legacy parser");
    bad_fat(good, 511); bad_fat(good, 1023); bad_fat(good, FAT_BYTES - 1);
#define BAD_FAT(change) do { memcpy(bad, good, FAT_BYTES); change; bad_fat(bad, FAT_BYTES); } while (0)
    BAD_FAT(bad[510] = 0); BAD_FAT(fx_le16(bad + 11, 0)); BAD_FAT(fx_le16(bad + 11, 513));
    BAD_FAT(bad[13] = 0); BAD_FAT(bad[13] = 3); BAD_FAT(fx_le16(bad + 14, 0));
    BAD_FAT(bad[16] = 0); BAD_FAT(bad[16] = 3); BAD_FAT(fx_le16(bad + 17, 1));
    BAD_FAT(fx_le16(bad + 19, 64)); BAD_FAT(fx_le16(bad + 22, 1));
    BAD_FAT(fx_le16(bad + 42, 1)); BAD_FAT(fx_le16(bad + 40, 0x81));
    BAD_FAT(fx_le32(bad + 36, 0)); BAD_FAT(fx_le32(bad + 32, 0));
    BAD_FAT(fx_le32(bad + 32, 2)); BAD_FAT(fx_le32(bad + 36, UINT32_MAX));
    BAD_FAT(fx_le32(bad + 32, UINT32_MAX)); BAD_FAT(fx_le32(bad + 44, 1));
    BAD_FAT(fx_le32(bad + 44, 64));
#undef BAD_FAT
    scenario("FAT fragmented/truncated/cyclic/bad chains never borrow or copy");
#define BAD_CHAIN(change) do { memcpy(bad, good, FAT_BYTES); K60AdspReader live = {0}; \
    CHECK(!k60_adsp_reader_fat(&live, bad, FAT_BYTES)); change; unchanged_error(&live, "mdt", 700, -7); } while (0)
    BAD_CHAIN(fat_entry(bad, 4, 7)); BAD_CHAIN(fat_entry(bad, 4, 0x0fffffff));
    BAD_CHAIN(fat_entry(bad, 4, 4)); BAD_CHAIN(fat_entry(bad, 4, 0));
    BAD_CHAIN(fat_entry(bad, 4, 0x0ffffff7)); BAD_CHAIN(fat_entry(bad, 4, 64));
    BAD_CHAIN(fat_entry(bad, 5, 6)); BAD_CHAIN(fat_entry(bad, 5, 4));
    BAD_CHAIN(fx_le32(bad + FAT_DIR + 28, UINT32_MAX));
    BAD_CHAIN(fx_le32(bad + FAT_DIR + 28, 0));
    BAD_CHAIN(fx_le16(bad + FAT_DIR + 26, 1));
    BAD_CHAIN(fx_le16(bad + FAT_DIR + 26, 64));
    BAD_CHAIN(bad[FAT_DIR + 11] = 16); BAD_CHAIN(bad[FAT_ROOT + 11] = 32);
    BAD_CHAIN(bad[13] = 3);
#undef BAD_CHAIN
    memcpy(bad, good, FAT_BYTES); K60AdspReader live = {0}; CHECK(!k60_adsp_reader_fat(&live, bad, FAT_BYTES));
    bad[FAT_ROOT] = 0; unchanged_error(&live, "mdt", 700, -6);
    memcpy(bad, good, FAT_BYTES); bad[FAT_DIR] = 0; unchanged_error(&live, "mdt", 700, -6);
    memcpy(bad, good, FAT_BYTES);
    for (unsigned i = 0; i < 512; i += 32) bad[FAT_ROOT + i] = 0xe5;
    fat_entry(bad, 2, 2); unchanged_error(&live, "mdt", 700, -7);
    memcpy(bad, good, FAT_BYTES); live.fat.data_start ^= 1; unchanged_error(&live, "mdt", 700, -7);
    free(bad); free(good);
}

typedef struct { K60AdspMdtPiece piece; void *context; unsigned calls[100]; } PieceSpy;
static int spy_piece(void *context, uint32_t index, const uint8_t **p, size_t *n)
{
    PieceSpy *spy = context; CHECK(index < 100); ++spy->calls[index]; CHECK(index != 24);
    return spy->piece(spy->context, index, p, n);
}
static void install_spy(PieceSpy *spy, K60OwnerImage *image)
{
    memset(spy, 0, sizeof *spy); spy->piece = image->piece; spy->context = image->context;
    image->piece = spy_piece; image->context = spy;
}
static void check_plan(const K60AdspMdtPlan *p)
{
    CHECK(p->headers == 26 && p->count == 24 && p->relocatable == 1);
    CHECK(p->span == IMAGE_SPAN && p->span == 51380224u && p->region_base == IMAGE_BASE);
    CHECK(p->region_bytes == IMAGE_SPAN && p->prefix_bytes + p->hash_bytes == META_BYTES);
    uint64_t copy = 0, zero = 0; unsigned b10 = 0, b24 = 0;
    for (unsigned i = 0; i < p->count; ++i) {
        const K60AdspMdtSegment *s = &p->segment[i]; copy += s->copy_bytes; zero += s->zero_bytes;
        CHECK(s->destination >= IMAGE_BASE && s->destination - IMAGE_BASE <= IMAGE_SPAN);
        CHECK((uint64_t)s->copy_bytes + s->zero_bytes <= IMAGE_SPAN - (s->destination - IMAGE_BASE));
        if (s->index == 10) {
            ++b10; CHECK(s->link_address == 0x86e0b2c0u && s->destination == UINT64_C(0xa080b2c0));
            CHECK(s->copy_bytes == 720 && s->zero_bytes == 2672 && s->source_is_piece);
        }
        if (s->index == 24) { ++b24; CHECK(!s->copy_bytes && s->zero_bytes == 7245824u && !s->source_is_piece); }
    }
    CHECK(copy == 23494284u && zero == 25925684u && b10 == 1 && b24 == 1);
    CHECK(p->span - copy - zero == 1960256u);
}
static void put_segment(uint8_t *dst, const K60AdspMdtSegment *s, const uint8_t *src, size_t n)
{
    CHECK(n == s->copy_bytes && (src || !n));
    size_t offset = (size_t)(s->destination - IMAGE_BASE);
    if (n) memcpy(dst + GUARD + offset, src, n);
    memset(dst + GUARD + offset + n, 0, s->zero_bytes);
}
static void check_destination(const uint8_t *dst, const K60AdspMdtPlan *plan)
{
    uint8_t *expect = allocate(IMAGE_SPAN + 2u * GUARD); memset(expect, SENTINEL, IMAGE_SPAN + 2u * GUARD);
    for (unsigned i = 0; i < plan->count; ++i) {
        const K60AdspMdtSegment *s = &plan->segment[i];
        if (s->copy_bytes) {
            char name[9] = "adsp.b00"; name[6] = (char)('0' + s->index / 10u); name[7] = (char)('0' + s->index % 10u);
            const Part *part = find_part(name); CHECK(part && part->bytes == s->copy_bytes);
            put_segment(expect, s, part->data, part->bytes);
        } else put_segment(expect, s, NULL, 0);
    }
    CHECK(filled(dst, GUARD, SENTINEL) && filled(dst + GUARD + IMAGE_SPAN, GUARD, SENTINEL));
    CHECK(!memcmp(dst, expect, IMAGE_SPAN + 2u * GUARD));
    /* The entire region comparison includes every untouched gap, not just totals. */
    size_t b10 = (size_t)(UINT64_C(0xa080b2c0) - IMAGE_BASE);
    CHECK(!memcmp(dst + GUARD + b10, find_part("adsp.b10")->data, 720));
    CHECK(fx_zero(dst + GUARD + b10 + 720, 2672)); free(expect);
}
static void captured_reads(K60AdspReader *r)
{
    scenario("every captured MDT/bNN byte is available at its exact length");
    for (unsigned i = 0; i < captured.count; ++i) {
        const Part *part = &captured.part[i]; const uint8_t *p = NULL; size_t n = 0;
        CHECK(!k60_adsp_reader_borrow(r, part->name, &p, &n));
        CHECK(n == part->bytes && !memcmp(p, part->data, n));
        uint8_t *out = allocate(n + 2); memset(out, 0xa7, n + 2);
        CHECK(!k60_adsp_reader_read(r, part->name, out + 1, (uint32_t)n));
        CHECK(out[0] == 0xa7 && out[n + 1] == 0xa7 && !memcmp(out + 1, part->data, n)); free(out);
    }
    unchanged_error(r, "adsp.b24", 1, -6); unchanged_error(r, "adsp.b10", 719, -5);
    unchanged_error(r, "adsp.b10", 721, -5);
}
static int faulty_piece(void *context, uint32_t index, const uint8_t **p, size_t *n)
{
    int error = *(int *)context; CHECK(index == 10); if (error) return error;
    *p = find_part("adsp.b10")->data; *n = 719; return 0;
}
static int near_limit_piece(void *context, uint32_t index, const uint8_t **p, size_t *n)
{
    (void)context; CHECK(index == 10); *p = (const uint8_t *)(uintptr_t)(UINTPTR_MAX - 2u); *n = 720; return 0;
}
static void segment_tests(const K60AdspReader *source)
{
    scenario("owner adapter init aliases, exact close, double open and reopen");
    K60AdspOwnerReader owner = {0}, bad = {0}; uint8_t *metadata = allocate(META_BYTES);
    CHECK(k60_adsp_owner_reader_init(&bad, source, (uint8_t *)(void *)source->base, META_BYTES) == -1);
    CHECK(fx_zero(&bad, sizeof bad));
    CHECK(k60_adsp_owner_reader_init(&bad, source, (uint8_t *)(void *)&bad, sizeof bad) == -1);
    CHECK(k60_adsp_owner_reader_init(&bad, source, metadata, 0) == -1);
    CHECK(!k60_adsp_owner_reader_init(&owner, source, metadata, META_BYTES));
    CHECK(k60_adsp_owner_reader_init(&owner, source, metadata, META_BYTES) == -1);
    memset(metadata, 0xd7, META_BYTES);
    CHECK(k60_adsp_owner_image_open(&owner, (K60OwnerImage *)(void *)metadata) == -1000);
    CHECK(filled(metadata, META_BYTES, 0xd7) && !owner.active);
    K60OwnerImage image = {0}, other, before;
    memset(&other, 0xa5, sizeof other); before = other;
    CHECK(!k60_adsp_owner_image_open(&owner, &image));
    K60OwnerImage image_before = image;
    CHECK(k60_adsp_owner_image_open(&owner, &other) == -1000 && !memcmp(&other, &before, sizeof other));
    CHECK(k60_adsp_owner_image_open(&owner, &image) == -1000 && !memcmp(&image, &image_before, sizeof image));
    K60OwnerImage copy = image; k60_adsp_owner_image_close(&owner, &copy);
    CHECK(owner.active == 1 && !memcmp(&image, &image_before, sizeof image));
    void *handle = image.handle; image.handle = NULL; k60_adsp_owner_image_close(&owner, &image);
    CHECK(owner.active == 1); image.handle = handle;
    PieceSpy spy; install_spy(&spy, &image);
    K60AdspMdtPlan plan;
    CHECK(!k60_adsp_mdt_prepare(image.mdt, image.bytes, IMAGE_BASE, IMAGE_SPAN, image.piece,
        image.context, metadata, META_BYTES, &plan)); check_plan(&plan);
    CHECK(!memcmp(metadata, find_part("adsp.mdt")->data, META_BYTES) && !spy.calls[24]);
    scenario("captured helper relocates exact copy+BSS with sentinel-preserved gaps");
    uint8_t *dst = allocate(IMAGE_SPAN + 2u * GUARD); memset(dst, SENTINEL, IMAGE_SPAN + 2u * GUARD);
    for (unsigned i = 0; i < plan.count; ++i) {
        const uint8_t *p = metadata; size_t n = 999;
        CHECK(!k60_adsp_image_segment(&image, &plan.segment[i], &p, &n));
        if (!plan.segment[i].copy_bytes) CHECK(!p && !n);
        put_segment(dst, &plan.segment[i], p, n);
    }
    check_destination(dst, &plan); CHECK(!spy.calls[24]); free(dst);
    K60AdspMdtPiece saved_piece = image.piece; void *saved_context = image.context;
    const uint8_t *p = metadata; size_t n = 123;
    k60_adsp_owner_image_close(&owner, &image); CHECK(!owner.active && !owner.opened_image && fx_zero(&image, sizeof image));
    CHECK(saved_piece(saved_context, 10, &p, &n) == -6 && p == metadata && n == 123);
    k60_adsp_owner_image_close(&owner, &image); CHECK(!owner.active);
    CHECK(!k60_adsp_owner_image_open(&owner, &other)); CHECK(owner.active == 1);
    CHECK(!other.piece(other.context, 10, &p, &n) && n == 720);
    CHECK(!memcmp(p, find_part("adsp.b10")->data, 720)); k60_adsp_owner_image_close(&owner, &other);

    scenario("segment helper propagates -5/-6/-7 and bounds errors unchanged");
    K60OwnerImage inline_image = {0}; inline_image.mdt = metadata; inline_image.bytes = META_BYTES;
    K60AdspMdtSegment seg = {0}; seg.file_offset = META_BYTES - 3; seg.copy_bytes = 3;
    CHECK(!k60_adsp_image_segment(&inline_image, &seg, &p, &n) && p == metadata + META_BYTES - 3 && n == 3);
    seg.file_offset = UINT32_MAX; p = metadata; n = 123;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -7 && p == metadata && n == 123);
    seg.file_offset = META_BYTES - 2;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -7 && p == metadata && n == 123);
    seg.source_is_piece = 1; seg.index = 10; seg.copy_bytes = 720;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -6 && p == metadata && n == 123);
    int error = 0; inline_image.context = &error; inline_image.piece = faulty_piece;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -5 && p == metadata && n == 123);
    error = -6; CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -6 && p == metadata && n == 123);
    error = -7; CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -7 && p == metadata && n == 123);
    scenario("segment pointer arithmetic overflow rejects without dereference or output writes");
    inline_image.piece = near_limit_piece;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -7 && p == metadata && n == 123);
    seg.source_is_piece = 0; seg.copy_bytes = 3; seg.file_offset = 0;
    inline_image.mdt = (const uint8_t *)(uintptr_t)(UINTPTR_MAX - 2u); inline_image.bytes = 3;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -7 && p == metadata && n == 123);
    inline_image.mdt = metadata; inline_image.bytes = SIZE_MAX;
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, &n) == -7 && p == metadata && n == 123);
    seg.copy_bytes = 0; seg.zero_bytes = 7245824; seg.index = 24;
    CHECK(!k60_adsp_image_segment(&inline_image, &seg, &p, &n) && !p && !n);
    CHECK(k60_adsp_image_segment(NULL, &seg, &p, &n) == -1);
    CHECK(k60_adsp_image_segment(&inline_image, NULL, &p, &n) == -1);
    CHECK(k60_adsp_image_segment(&inline_image, &seg, NULL, &n) == -1);
    CHECK(k60_adsp_image_segment(&inline_image, &seg, &p, NULL) == -1);
    free(metadata);
}

typedef struct {
    OwnerFixture fx; /* first: reuse proven SMEM/exclusive/vote/lock/publish fake */
    K60AdspOwnerReader reader;
    uint8_t metadata[META_BYTES];
    uint8_t *destination;
    PieceSpy spy;
    unsigned order;
} ReaderEngine;
static ReaderEngine engine_storage[4], *engine;
static unsigned engine_count;
static int engine_reader(void *context, K60OwnerImage *image)
{
    ReaderEngine *e = context; fx_outside(&e->fx); ++e->fx.reader_calls;
    int rc = k60_adsp_owner_image_open(&e->reader, image);
    if (!rc) install_spy(&e->spy, image);
    return rc;
}
static void engine_close(void *context, K60OwnerImage *image)
{ ReaderEngine *e = context; fx_close(&e->fx, image); k60_adsp_owner_image_close(&e->reader, image); }
static int engine_init(void *context, const uint8_t *metadata, size_t n)
{
    ReaderEngine *e = context; fx_outside(&e->fx); CHECK(!e->order && !e->fx.running);
    CHECK(metadata == e->metadata && n == META_BYTES && !memcmp(metadata, find_part("adsp.mdt")->data, n));
    ++e->fx.init_calls; e->order = 1; return 0;
}
static int engine_mem(void *context, uint64_t base, uint64_t bytes)
{
    ReaderEngine *e = context; fx_outside(&e->fx); CHECK(e->order == 1 && !e->fx.running);
    CHECK(base == IMAGE_BASE && bytes == IMAGE_SPAN); ++e->fx.mem_calls; e->order = 2; return 0;
}
static int engine_load(void *context, uint64_t dest, const uint8_t *source, uint32_t copy, uint32_t zero)
{
    ReaderEngine *e = context; fx_outside(&e->fx); CHECK(e->order == 2 && !e->fx.running);
    CHECK(e->fx.load_calls < e->fx.owner->image_plan.count);
    const K60AdspMdtSegment *s = &e->fx.owner->image_plan.segment[e->fx.load_calls];
    CHECK(dest == s->destination && copy == s->copy_bytes && zero == s->zero_bytes);
    const uint8_t *expected = NULL; size_t n = 0;
    CHECK(!k60_adsp_image_segment(&e->fx.owner->image, s, &expected, &n));
    CHECK(source == expected && n == copy); put_segment(e->destination, s, source, n);
    ++e->fx.load_calls; return 0;
}
static int engine_auth(void *context)
{
    ReaderEngine *e = context; fx_outside(&e->fx); CHECK(e->order == 2 && e->fx.load_calls == 24);
    CHECK(e->fx.init_calls == 1 && e->fx.mem_calls == 1 && !e->spy.calls[24]);
    ++e->fx.auth_calls; e->fx.running = 1; e->order = 3; return e->fx.auth_rc;
}
static void engine_case(const K60AdspReader *source, const char *name)
{
    /* Published/poisoned fixtures remain pinned until process exit. */
    CHECK(engine_count < sizeof engine_storage / sizeof *engine_storage);
    engine = &engine_storage[engine_count++]; fx_case(&engine->fx, name); scenario(name);
    CHECK(!k60_adsp_owner_reader_init(&engine->reader, source, engine->metadata, META_BYTES));
    engine->fx.ops.image_reader = engine_reader; engine->fx.ops.image_close = engine_close;
    engine->fx.ops.init_image = engine_init; engine->fx.ops.mem_setup = engine_mem;
    engine->fx.ops.load = engine_load; engine->fx.ops.auth_and_reset = engine_auth;
    engine->destination = allocate(IMAGE_SPAN + 2u * GUARD);
    memset(engine->destination, SENTINEL, IMAGE_SPAN + 2u * GUARD);
}
static void engine_started(void)
{
    fx_start(&engine->fx); check_plan(&engine->fx.session.image_plan);
    check_destination(engine->destination, &engine->fx.session.image_plan);
    CHECK(engine->fx.load_calls == 24 && !engine->spy.calls[24] && engine->reader.active == 1);
    CHECK(!engine->fx.close_calls && engine->fx.session.image_open);
    CHECK(engine->fx.lock_calls == 2 && engine->fx.unlock_calls == 2 && !engine->fx.locked);
}
static void engine_tests(const K60AdspReader *source)
{
    engine_case(source, "captured reader drives real owner stages 1-3 and closes exactly once on abort");
    engine_started(); k60_owner_abort(&engine->fx.session); fx_failed(&engine->fx);
    CHECK(engine->fx.close_calls == 1 && !engine->reader.active && !engine->reader.opened_image);
    CHECK(!strcmp(engine->fx.cleanup, "STUCRE")); k60_owner_abort(&engine->fx.session);
    CHECK(engine->fx.close_calls == 1); K60OwnerImage reopened = {0};
    CHECK(!k60_adsp_owner_image_open(&engine->reader, &reopened)); k60_adsp_owner_image_close(&engine->reader, &reopened);
    free(engine->destination);

    engine_case(source, "published owner pins reader and metadata with no release path"); engine_started();
    CHECK(!k60_owner_build_handoff(&engine->fx.session, &engine->fx.plan));
    CHECK(!k60_owner_publish(&engine->fx.session, &engine->fx.publish, &engine->fx));
    CHECK(engine->fx.session.phase == K60OwnerPublished && engine->fx.property_writes == 1);
    k60_owner_abort(&engine->fx.session);
    CHECK(engine->reader.active == 1 && engine->fx.session.image_open && !engine->fx.close_calls);
    CHECK(!engine->fx.shutdown_calls && !engine->fx.resources_release_calls && !engine->fx.release_calls);
    const uint8_t *p = NULL; size_t n = 0;
    CHECK(!engine->fx.session.image.piece(engine->fx.session.image.context, 10, &p, &n) && n == 720);
    CHECK(!memcmp(p, find_part("adsp.b10")->data, n));
    CHECK(!memcmp(engine->metadata, find_part("adsp.mdt")->data, META_BYTES));
    free(engine->destination);

    engine_case(source, "poisoned owner pins reader while shutdown cannot prove stopped");
    fx_prepare(&engine->fx); engine->fx.auth_rc = -1; engine->fx.shutdown_rc = -1;
    CHECK(k60_owner_auth_and_start(&engine->fx.session) == -1000);
    CHECK(engine->fx.session.phase == K60OwnerPoisoned && engine->reader.active == 1);
    CHECK(engine->fx.session.image_open && !engine->fx.close_calls && !engine->fx.unmap_calls);
    CHECK(!engine->fx.release_calls && !engine->fx.resources_release_calls && !engine->spy.calls[24]);
    CHECK(!engine->fx.session.image.piece(engine->fx.session.image.context, 10, &p, &n) && n == 720);
    k60_owner_abort(&engine->fx.session); CHECK(engine->fx.shutdown_calls == 1 && !engine->fx.close_calls);
    free(engine->destination);

    engine_case(source, "insufficient metadata fails claim before mappings and closes reader");
    engine->reader.capacity = META_BYTES - 1; memset(engine->metadata, 0xdd, META_BYTES);
    CHECK(k60_owner_claim(&engine->fx.session, &engine->fx.config, &engine->fx.ops, &engine->fx) == -1000);
    CHECK(engine->fx.close_calls == 1 && !engine->reader.active && !engine->fx.map_calls && !engine->fx.lock_calls);
    CHECK(filled(engine->metadata, META_BYTES, 0xdd)); free(engine->destination);

    scenario("missing MDT owner open is transactional and repeatable");
    Part only = {"adsp.b10", find_part("adsp.b10")->data, 720}; Carrier missing = make_blob(&only, 1);
    K60AdspReader r = {0}; K60AdspOwnerReader owner = {0}; uint8_t metadata[META_BYTES];
    CHECK(!k60_adsp_reader_blob(&r, missing.data, missing.bytes));
    CHECK(!k60_adsp_owner_reader_init(&owner, &r, metadata, sizeof metadata));
    K60OwnerImage image, before; memset(&image, 0x55, sizeof image); before = image;
    for (unsigned i = 0; i < 2; ++i) {
        CHECK(k60_adsp_owner_image_open(&owner, &image) == -1000 && !owner.active);
        CHECK(!owner.opened_image && !memcmp(&image, &before, sizeof image));
    }
    free(missing.data);
}
int main(int argc, char **argv)
{
    fx_name = "usage"; CHECK(argc == 2);
    load_capture(argv[1]); blob_tests(); fat_tests();
    K60AdspReader r = {0}; CHECK(!k60_adsp_reader_blob(&r, captured.blob.data, captured.blob.bytes));
    captured_reads(&r); segment_tests(&r); engine_tests(&r);
    printf("TESTS OK adsp-reader: %u scenarios; %u captured entries; 24 segments; "
        "copy=23494284 zero=25925684 span=51380224 gaps=1960256; no b24 read%s\n",
        scenarios, captured.count,
#ifdef K60_ADSP_TEST_LINKED
        "; linked K60A read passed"
#else
        ""
#endif
    );
    /* Published/poisoned sessions pin captured carrier and metadata to exit. */
    return 0;
}
