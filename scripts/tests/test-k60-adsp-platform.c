/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline only: real platform ops/owner stages around explicit fake low-level
 * services. argv[1] is captured firmware, argv[2] optional generated K60A bin.
 * Linked variant gets the ACTUAL bin symbols from the runner's ELF wrapper. */
#include <errno.h>
#include "test-k60-owner-fixture.h"
#include "../../drivers/PongPower/K60AdspPlatform.h"

#define IMAGE_BASE UINT64_C(0x9fd00000)
#define IMAGE_BYTES 0x3100000u
#define META_BYTES 5404u
#define GUARD 32u
#define SENTINEL 0xccu
#define ERROR (-73)

typedef struct { char name[9]; uint8_t *data; size_t bytes; } Part;
static Part parts[K60_ADSP_BLOB_MAX_ENTRIES];
static unsigned part_count, cases;
static uint8_t *carrier;
static size_t carrier_bytes;
static K60AdspReader captured;
static const K60OwnerOps *ops;
#ifdef K60_ADSP_PLATFORM_TEST_LINKED
extern const uint8_t k60_adsp_blob[];
extern const uint64_t k60_adsp_blob_len;
#endif

static void scenario(const char *name) { fx_name=name; ++cases; }
static void *allocate(size_t n) { void *p=malloc(n); CHECK(p); return p; }
static int filled(const void *p,size_t n,uint8_t v)
{ const uint8_t *b=p; while(n--) if(*b++!=v)return 0; return 1; }
static size_t align8(size_t n) { CHECK(n<=SIZE_MAX-7u); return (n+7u)&~(size_t)7u; }
static void le64(uint8_t *p,uint64_t v)
{ fx_le32(p,(uint32_t)v);fx_le32(p+4,(uint32_t)(v>>32)); }
static Part *part(const char *name)
{ for(unsigned i=0;i<part_count;i++)if(!strcmp(parts[i].name,name))return &parts[i];return NULL; }
static uint8_t *read_file(const char *path,size_t *bytes,int optional)
{
    errno=0;FILE *fp=fopen(path,"rb");
    if(!fp && optional && errno==ENOENT)return NULL;
    CHECK(fp);CHECK(!fseek(fp,0,SEEK_END));long n=ftell(fp);
    CHECK(n>0 && (uint64_t)n<=UINT32_MAX);CHECK(!fseek(fp,0,SEEK_SET));
    uint8_t *p=allocate((size_t)n);CHECK(fread(p,1,(size_t)n,fp)==(size_t)n);
    CHECK(!ferror(fp) && !fclose(fp));*bytes=(size_t)n;return p;
}
static void load_part(const char *dir,const char *name,int optional)
{
    char path[4096];int n=snprintf(path,sizeof path,"%s/%s",dir,name);
    CHECK(n>0 && (size_t)n<sizeof path && part_count<K60_ADSP_BLOB_MAX_ENTRIES);
    Part p={0};p.data=read_file(path,&p.bytes,optional);if(!p.data)return;
    memcpy(p.name,name,9);parts[part_count++]=p;
}
static void load_capture(const char *dir,const char *bin)
{
    scenario("captured 26-file K60A is byte exact and has no b24 input");
    load_part(dir,"adsp.mdt",0);
    for(unsigned i=0;i<100;i++) {
        char name[9]="adsp.b00";name[6]=(char)('0'+i/10u);name[7]=(char)('0'+i%10u);
        load_part(dir,name,1);
    }
    CHECK(part_count==26 && !part("adsp.b24") && part("adsp.mdt")->bytes==META_BYTES);
    size_t records[64],names[64],bodies[64],cursor=12;
    for(unsigned i=0;i<part_count;i++) {
        records[i]=cursor;cursor=align8(cursor+24);names[i]=cursor;
        cursor=align8(cursor+9);bodies[i]=cursor;cursor=align8(cursor+parts[i].bytes);
    }
    carrier_bytes=cursor;CHECK(carrier_bytes==23506184u);
    carrier=allocate(carrier_bytes);memset(carrier,0,carrier_bytes);
    memcpy(carrier,"K60A",4);fx_le32(carrier+4,part_count);
    for(unsigned i=0;i<part_count;i++) {
        uint8_t *p=carrier+records[i];fx_le32(p,9);fx_le32(p+4,0644);
        le64(p+8,parts[i].bytes);le64(p+16,parts[i].bytes);
        memcpy(carrier+names[i],parts[i].name,9);memcpy(carrier+bodies[i],parts[i].data,parts[i].bytes);
    }
    CHECK(!k60_adsp_reader_blob(&captured,carrier,carrier_bytes));
    if(bin) {size_t n=0;uint8_t *p=read_file(bin,&n,0);CHECK(n==carrier_bytes);
        CHECK(!memcmp(p,carrier,n));free(p);}
#ifdef K60_ADSP_PLATFORM_TEST_LINKED
    CHECK(k60_adsp_blob_len==carrier_bytes && !memcmp(k60_adsp_blob,carrier,carrier_bytes));
#endif
}

typedef struct {
    OwnerFixture fx; /* Existing fixture seeds SMEM; no changes to its header. */
    K60AdspPlatform platform;
    uint8_t *destination;
    _Alignas(4) uint32_t mutex_word;
    unsigned available_calls,exclusive_calls,release_calls,resources_calls,resources_releases;
    unsigned stopped_calls,live_calls,map_calls,unmap_shared,unmap_mutex,firmware_maps,firmware_unmaps;
    unsigned active_shared,active_mutex,active_firmware,sync_calls,lock_calls,unlock_calls,locked;
    unsigned init_calls,mem_calls,auth_calls,shutdown_calls,delay_calls,order;
    unsigned fail_map_on,bad_map_on,fail_sync_on,fail_lock_on,ready_after_delay;
    int available_value,exclusive_rc,resources_rc,init_rc,mem_rc,auth_rc,shutdown_rc;
    int stopped_value,stop_after_shutdown,live_value,zero_epoch,zero_cookie;
    int shared_handle,mutex_handle;
    char cleanup[64];size_t cleanup_used;
    K60AdspMdtPiece original_piece;void *original_context;unsigned piece_calls[100];
} Fixture;
static Fixture *pinned[8];static unsigned pinned_count;
static void outside(Fixture *f)
{ CHECK(!f->locked && !f->platform.locked && !f->fx.session.locked); }
static void trace(Fixture *f,char c)
{ CHECK(f->cleanup_used+1<sizeof f->cleanup);f->cleanup[f->cleanup_used++]=c;f->cleanup[f->cleanup_used]=0; }
static int service_available(void *ctx,const K60BatteryConfig *c)
{
    Fixture *f=ctx;outside(f);++f->available_calls;
    CHECK(c->smem_base==f->fx.config.smem_base && c->adsp_base==IMAGE_BASE);
    return f->available_value;
}
static int service_exclusive(void *ctx,const K60BatteryConfig *c,uint32_t *epoch,void **cookie)
{
    Fixture *f=ctx;outside(f);++f->exclusive_calls;CHECK(c->adsp_bytes==IMAGE_BYTES);
    if(f->exclusive_rc)return f->exclusive_rc;
    *epoch=f->zero_epoch?0:f->fx.epoch;*cookie=f->zero_cookie?NULL:f;return 0;
}
static void service_exclusive_release(void *ctx,void *cookie)
{
    Fixture *f=ctx;outside(f);CHECK(cookie==f && !f->active_shared && !f->active_mutex);
    CHECK(!f->platform.resources_held);
    if(f->platform.reserved)CHECK(!f->platform.reader.active);
    ++f->release_calls;trace(f,'E');
}
static int service_resources(void *ctx,void *cookie)
{ Fixture *f=ctx;outside(f);CHECK(cookie==f);++f->resources_calls;return f->resources_rc; }
static void service_resources_release(void *ctx,void *cookie)
{
    Fixture *f=ctx;outside(f);CHECK(cookie==f && f->stopped_value==1);
    CHECK(!f->active_shared && !f->active_mutex && !f->active_firmware);
    /* Image close must be between unmap and resource release. */
    CHECK(!f->platform.reader.active && !f->platform.reader.opened_image);
    CHECK(fx_zero(&f->fx.session.image,sizeof f->fx.session.image));
    ++f->resources_releases;trace(f,'R');
}
static int service_stopped(void *ctx,void *cookie)
{
    Fixture *f=ctx;outside(f);CHECK(cookie==f);++f->stopped_calls;
    if(f->fx.session.auth_attempted && f->shutdown_calls)trace(f,'T');
    return f->stopped_value;
}
static int service_live(void *ctx,void *cookie,uint32_t epoch)
{ Fixture *f=ctx;outside(f);CHECK(cookie==f && epoch==f->fx.epoch);++f->live_calls;return f->live_value; }
static int service_map(void *ctx,uint64_t physical,size_t n,unsigned kind,K60AdspPlatformMapping *m)
{
    Fixture *f=ctx;outside(f);++f->map_calls;CHECK(!m->base && !m->bytes && !m->handle);
    if(f->map_calls==f->fail_map_on)return ERROR;
    CHECK(f->stopped_value==1);
    if(kind==K60AdspMapShared) {
        CHECK(physical==f->fx.config.smem_base && n==FX_SMEM_BYTES && !f->active_shared);
        m->base=fx_bytes(&f->fx);m->handle=&f->shared_handle;++f->active_shared;
    } else if(kind==K60AdspMapDevice) {
        CHECK(physical==f->fx.config.mutex_base && n==4 && f->active_shared && !f->active_mutex);
        m->base=(volatile uint8_t *)&f->mutex_word;m->handle=&f->mutex_handle;++f->active_mutex;
    } else {
        CHECK(kind==K60AdspMapFirmware && f->destination && f->order==2 && !f->active_firmware);
        CHECK(physical>=IMAGE_BASE && n && n<=K60_ADSP_PLATFORM_WINDOW_BYTES);
        CHECK(physical-IMAGE_BASE<=IMAGE_BYTES && n<=IMAGE_BYTES-(physical-IMAGE_BASE));
        m->base=f->destination+GUARD+(size_t)(physical-IMAGE_BASE);m->handle=(void *)m->base;
        ++f->active_firmware;++f->firmware_maps;
    }
    m->bytes=f->map_calls==f->bad_map_on?n-1:n;return 0;
}
static void service_unmap(void *ctx,K60AdspPlatformMapping *m)
{
    Fixture *f=ctx;outside(f);CHECK(m->handle && m->base);
    if(m->handle==&f->mutex_handle) {
        CHECK(f->active_mutex && f->platform.reader.active);--f->active_mutex;++f->unmap_mutex;trace(f,'M');
    } else if(m->handle==&f->shared_handle) {
        CHECK(f->active_shared && !f->active_mutex && f->platform.reader.active);
        --f->active_shared;++f->unmap_shared;trace(f,'U');
    } else {CHECK(f->active_firmware==1);--f->active_firmware;++f->firmware_unmaps;}
    /* Deliberately leave the struct intact: production release_map must clear it. */
}
static int service_sync(void *ctx,const K60AdspPlatformMapping *m,size_t at,size_t n)
{
    Fixture *f=ctx;outside(f);CHECK(f->active_firmware && at==0 && n==m->bytes);
    ++f->sync_calls;return f->sync_calls==f->fail_sync_on?ERROR:0;
}
static int service_lock(void *ctx,const K60AdspPlatformMapping *m)
{
    Fixture *f=ctx;outside(f);CHECK(m->handle==&f->mutex_handle && f->active_mutex);
    ++f->lock_calls;if(f->lock_calls==f->fail_lock_on)return ERROR;f->locked=1;return 0;
}
static void service_unlock(void *ctx,const K60AdspPlatformMapping *m)
{
    Fixture *f=ctx;CHECK(f->locked && f->platform.locked && !f->fx.session.locked);
    CHECK(m->handle==&f->mutex_handle);f->locked=0;++f->unlock_calls;
}
static int service_init(void *ctx,const uint8_t *metadata,size_t n)
{
    Fixture *f=ctx;outside(f);CHECK(f->order==0 && metadata==f->platform.metadata && n==META_BYTES);
    CHECK(!memcmp(metadata,part("adsp.mdt")->data,n));++f->init_calls;
    if(f->init_rc)return f->init_rc;
    f->order=1;return 0;
}
static int service_mem(void *ctx,uint64_t base,uint64_t span)
{
    Fixture *f=ctx;outside(f);CHECK(f->order==1 && base==IMAGE_BASE && span==IMAGE_BYTES);
    ++f->mem_calls;if(f->mem_rc)return f->mem_rc;f->order=2;return 0;
}
static int service_auth(void *ctx)
{
    Fixture *f=ctx;outside(f);CHECK(f->order==2 && !f->active_firmware);
    CHECK(f->firmware_maps==f->firmware_unmaps && f->sync_calls==f->firmware_maps);
    ++f->auth_calls;f->order=3;
    /* Even failed AUTH may have started execution; only independent stop proves safety. */
    f->stopped_value=0;return f->auth_rc;
}
static int service_shutdown(void *ctx)
{
    Fixture *f=ctx;outside(f);CHECK(f->platform.reader.active && f->active_shared && f->active_mutex);
    ++f->shutdown_calls;trace(f,'S');if(f->stop_after_shutdown)f->stopped_value=1;return f->shutdown_rc;
}
static void service_delay(void *ctx,unsigned us)
{
    Fixture *f=ctx;outside(f);CHECK(us==1000);++f->delay_calls;
    if(f->ready_after_delay && f->delay_calls==f->ready_after_delay)
        fx_put(&f->fx,f->fx.remote_offset+36,2);
}
static K60AdspPlatformServices services(void)
{
    K60AdspPlatformServices s={K60_ADSP_PLATFORM_VERSION,sizeof(K60AdspPlatformServices),
        service_available,service_exclusive,service_exclusive_release,service_resources,
        service_resources_release,service_stopped,service_live,service_map,service_unmap,
        service_sync,service_lock,service_unlock,service_init,service_mem,service_auth,
        service_shutdown,service_delay};return s;
}
static Fixture *new_case(const char *name,int linked)
{
    scenario(name);Fixture *f=allocate(sizeof *f);memset(f,0,sizeof *f);fx_case(&f->fx,name);
    f->available_value=f->stopped_value=f->live_value=f->stop_after_shutdown=1;
    K60AdspPlatformServices s=services();
    CHECK(!k60_adsp_platform_init(&f->platform,&s,f,linked?NULL:&captured));
    CHECK(f->platform.initialized && !f->map_calls && !f->auth_calls);return f;
}
static void complete_ops(void)
{
    scenario("every production owner callback exists");ops=k60_adsp_platform_ops();
    CHECK(ops && ops->version==K60_OWNER_OPS_VERSION && ops->bytes==sizeof *ops);
    CHECK(ops->available && ops->image_reader && ops->image_close && ops->exclusive && ops->exclusive_release);
    CHECK(ops->resources && ops->resources_release && ops->stopped && ops->live && ops->map_smem);
    CHECK(ops->unmap_smem && ops->lock && ops->unlock && ops->init_image && ops->mem_setup);
    CHECK(ops->load && ops->auth_and_reset && ops->shutdown && ops->ready && ops->report);
}
static void cleared(Fixture *f)
{
    K60AdspPlatform *p=&f->platform;K60OwnerSession *s=&f->fx.session;
    /* Owner session cookie/epoch are historical diagnostics after failure. The
     * platform cookie/epoch below own the lease and MUST be cleared. */
    CHECK(s->phase==K60OwnerFailed && fx_zero(&s->lease,sizeof s->lease));
    CHECK(!s->reserved && !s->resources_held && !s->mapped && !s->image_open && !s->locked && !s->evidence);
    CHECK(fx_zero(&s->image,sizeof s->image) && !s->smem.base && !s->smem.size);
    CHECK(!p->reserved && !p->resources_held && !p->locked && !p->image_initialized && !p->cookie && !p->epoch);
    CHECK(fx_zero(&p->smem,sizeof p->smem) && fx_zero(&p->mutex,sizeof p->mutex));
    CHECK(!p->reader.active && !p->reader.opened_image && !f->locked);
    CHECK(!f->active_shared && !f->active_mutex && !f->active_firmware);
    CHECK(f->firmware_maps==f->firmware_unmaps);
    CHECK(!memcmp(fx_bytes(&f->fx)+f->fx.remote_offset,f->fx.remote_before,36));
}
static void dispose(Fixture *f) { cleared(f);free(f->destination);free(f); }
static void claim(Fixture *f)
{ CHECK(!k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)); }
static void prepare(Fixture *f) { claim(f);CHECK(!k60_owner_prepare_pas1(&f->fx.session)); }
static int spy_piece(void *ctx,uint32_t index,const uint8_t **p,size_t *n)
{
    Fixture *f=ctx;outside(f);CHECK(index<100);++f->piece_calls[index];
    return f->original_piece(f->original_context,index,p,n);
}
static void spy(Fixture *f)
{
    f->original_piece=f->fx.session.image.piece;f->original_context=f->fx.session.image.context;
    f->fx.session.image.piece=spy_piece;f->fx.session.image.context=f;
}
static void plan_check(Fixture *f)
{
    K60AdspMdtPlan *p=&f->fx.session.image_plan;uint64_t copy=0,zero=0;unsigned b10=0,b24=0;
    CHECK(p->headers==26 && p->count==24 && p->relocatable && p->span==IMAGE_BYTES);
    CHECK(p->prefix_bytes+p->hash_bytes==META_BYTES && p->region_base==IMAGE_BASE);
    for(unsigned i=0;i<p->count;i++) {
        K60AdspMdtSegment *s=&p->segment[i];copy+=s->copy_bytes;zero+=s->zero_bytes;
        if(s->index==10) {++b10;CHECK(s->link_address==0x86e0b2c0u && s->destination==UINT64_C(0xa080b2c0));
            CHECK(s->copy_bytes==720 && s->zero_bytes==2672 && s->source_is_piece);}
        if(s->index==24) {++b24;CHECK(!s->copy_bytes && s->zero_bytes==7245824u && !s->source_is_piece);}
    }
    CHECK(copy==23494284u && zero==25925684u && b10==1 && b24==1);
    CHECK(p->span-copy-zero==1960256u);
}
static void destination(Fixture *f)
{ f->destination=allocate(IMAGE_BYTES+2u*GUARD);memset(f->destination,SENTINEL,IMAGE_BYTES+2u*GUARD); }
static void memory_check(Fixture *f)
{
    uint8_t *expect=allocate(IMAGE_BYTES+2u*GUARD);memset(expect,SENTINEL,IMAGE_BYTES+2u*GUARD);
    K60AdspMdtPlan *p=&f->fx.session.image_plan;
    for(unsigned i=0;i<p->count;i++) {
        K60AdspMdtSegment *s=&p->segment[i];size_t at=GUARD+(size_t)(s->destination-IMAGE_BASE);
        CHECK(at>=GUARD && s->copy_bytes+s->zero_bytes<=IMAGE_BYTES+GUARD-at);
        if(s->copy_bytes) {char name[9]="adsp.b00";name[6]=(char)('0'+s->index/10u);name[7]=(char)('0'+s->index%10u);
            Part *input=part(name);CHECK(input && input->bytes==s->copy_bytes);
            memcpy(expect+at,input->data,input->bytes);CHECK(f->piece_calls[s->index]==1);}
        memset(expect+at+s->copy_bytes,0,s->zero_bytes);
    }
    CHECK(filled(f->destination,GUARD,SENTINEL));CHECK(filled(f->destination+GUARD+IMAGE_BYTES,GUARD,SENTINEL));
    CHECK(!memcmp(f->destination,expect,IMAGE_BYTES+2u*GUARD));
    size_t b10=GUARD+(size_t)(UINT64_C(0xa080b2c0)-IMAGE_BASE);
    CHECK(!memcmp(f->destination+b10,part("adsp.b10")->data,720));
    CHECK(fx_zero(f->destination+b10+720,2672));CHECK(!f->piece_calls[24]);free(expect);
}
static void start(Fixture *f)
{ prepare(f);plan_check(f);spy(f);destination(f);CHECK(!k60_owner_auth_and_start(&f->fx.session));memory_check(f); }

static void availability_tests(void)
{
    scenario("no services means unavailable and no map or SCM");
    Fixture *f=allocate(sizeof *f);memset(f,0,sizeof *f);fx_case(&f->fx,fx_name);
    CHECK(!k60_adsp_platform_init(&f->platform,NULL,f,&captured));
    CHECK(!ops->available(&f->platform,&f->fx.config));
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(!f->map_calls && !f->init_calls && !f->auth_calls && !f->exclusive_calls);dispose(f);

    scenario("missing carrier means unavailable even with complete services");
    f=allocate(sizeof *f);memset(f,0,sizeof *f);fx_case(&f->fx,fx_name);
    K60AdspPlatformServices s=services();K60AdspReader empty={0};
    CHECK(k60_adsp_platform_init(&f->platform,&s,f,&empty)!=0);
    CHECK(f->platform.initialized && !ops->available(&f->platform,&f->fx.config));
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(!f->available_calls && !f->map_calls && !f->init_calls && !f->auth_calls);dispose(f);
#ifndef K60_ADSP_PLATFORM_TEST_LINKED
    scenario("absent real linked carrier fails closed before service acquisition");
    f=allocate(sizeof *f);memset(f,0,sizeof *f);fx_case(&f->fx,fx_name);
    CHECK(k60_adsp_platform_init(&f->platform,&s,f,NULL)==K60AdspReaderMissing);
    CHECK(!ops->available(&f->platform,&f->fx.config));
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(!f->map_calls && !f->init_calls && !f->auth_calls && !f->exclusive_calls);dispose(f);
#endif
    scenario("incomplete service tables are rejected before initialization");
#define MISSING(field) do {K60AdspPlatform p={0};s=services();s.field=NULL;     CHECK(k60_adsp_platform_init(&p,&s,NULL,&captured)==-1000 && !p.initialized);}while(0)
    MISSING(available);MISSING(exclusive);MISSING(exclusive_release);MISSING(resources);
    MISSING(resources_release);MISSING(stopped);MISSING(live);MISSING(map);MISSING(unmap);
    MISSING(sync);MISSING(lock);MISSING(unlock);MISSING(init_image);MISSING(mem_setup);
    MISSING(auth_and_reset);MISSING(shutdown);MISSING(delay_us);
#undef MISSING
    K60AdspPlatform p={0};s=services();s.version++;CHECK(k60_adsp_platform_init(&p,&s,NULL,&captured)==-1000);
    s=services();s.bytes--;CHECK(k60_adsp_platform_init(&p,&s,NULL,&captured)==-1000);
    f=new_case("platform initialize is one-shot",0);CHECK(k60_adsp_platform_init(&f->platform,&s,f,&captured)==-1000);
    claim(f);k60_owner_abort(&f->fx.session);dispose(f);
}
static void acquisition_tests(void)
{
    Fixture *f=new_case("service availability must be exactly one",0);f->available_value=2;
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(!f->exclusive_calls && !f->map_calls && !f->init_calls);dispose(f);
    f=new_case("exclusive acquire failure closes captured image",0);f->exclusive_rc=ERROR;
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(f->exclusive_calls==1 && !f->release_calls && !f->map_calls);dispose(f);
    f=new_case("zero epoch rolls successful exclusive token back",0);f->zero_epoch=1;
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(f->release_calls==1 && !f->resources_calls && !f->map_calls);dispose(f);
    f=new_case("resource acquisition failure releases exclusion",0);f->resources_rc=ERROR;
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(f->resources_calls==1 && !f->resources_releases && f->release_calls==1 && !f->map_calls);dispose(f);
    for(unsigned n=1;n<=2;n++) {
        f=new_case(n==1?"first map failure rolls back all ownership":"second map failure unmaps first before ownership release",0);
        f->fail_map_on=n;CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
        CHECK(f->map_calls==n && f->unmap_shared==n-1 && !f->unmap_mutex);
        CHECK(f->resources_releases==1 && f->release_calls==1 && !f->init_calls);
        CHECK(!strcmp(f->cleanup,n==1?"RE":"URE"));dispose(f);
    }
    for(unsigned n=1;n<=2;n++) {
        f=new_case("malformed successful mapping is released transactionally",0);f->bad_map_on=n;
        CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
        CHECK(f->unmap_shared==1 && f->unmap_mutex==n-1);dispose(f);
    }
    f=new_case("failed first TCSR lock unmaps and releases",0);f->fail_lock_on=1;
    CHECK(k60_owner_claim(&f->fx.session,&f->fx.config,ops,&f->platform)==-1000);
    CHECK(f->lock_calls==1 && !f->unlock_calls && !strcmp(f->cleanup,"MURE"));dispose(f);
}
static void direct_guards(void)
{
    Fixture *f=new_case("all non-unlock callbacks have no effects while TCSR is locked",0);
    prepare(f);K60AdspPlatform *p=&f->platform;CHECK(!ops->lock(p));
    Fixture *before=allocate(sizeof *before);memcpy(before,f,sizeof *before);
    K60OwnerImage image;memset(&image,0xa5,sizeof image);
    uint32_t epoch=0xdeadbeef,bytes=0xabcdef01,restart=0x12345678;void *cookie=&image;
    CHECK(!ops->available(p,&f->fx.config));CHECK(ops->image_reader(p,&image)==-1000);
    ops->image_close(p,&f->fx.session.image);
    CHECK(ops->exclusive(p,&f->fx.config,&epoch,&cookie)==-1000);
    ops->exclusive_release(p,f);CHECK(ops->resources(p,f)==-1000);ops->resources_release(p,f);
    CHECK(!ops->stopped(p,f) && !ops->live(p,f,f->fx.epoch));
    CHECK(ops->map_smem(p,&f->fx.config,&f->fx.session.smem)==-1000);
    ops->unmap_smem(p,&f->fx.session.smem);CHECK(ops->lock(p)==-1000);
    CHECK(ops->init_image(p,p->metadata,META_BYTES)==-1000);
    CHECK(ops->mem_setup(p,IMAGE_BASE,IMAGE_BYTES)==-1000);
    CHECK(ops->load(p,UINT64_C(0xa080b2c0),part("adsp.b10")->data,720,2672)==-1000);
    CHECK(ops->auth_and_reset(p)==-1000 && ops->shutdown(p)==-1000);
    CHECK(ops->ready(p,&f->fx.config,&f->fx.session.smem,&bytes,&restart)==-1000);
    ops->report(p,4,0);
    CHECK(!memcmp(before,f,sizeof *f) && filled(&image,sizeof image,0xa5));
    CHECK(epoch==0xdeadbeef && cookie==&image && bytes==0xabcdef01 && restart==0x12345678);
    free(before);ops->unlock(p);CHECK(!f->locked && !p->locked);
    k60_owner_abort(&f->fx.session);dispose(f);

    f=new_case("ready rejects a config different from the acquired lease without service effects",0);
    claim(f);K60BatteryConfig changed=f->fx.config;changed.ipcc_signal^=1u;
    before=allocate(sizeof *before);memcpy(before,f,sizeof *before);
    CHECK(ops->ready(&f->platform,&changed,&f->fx.session.smem,&bytes,&restart)==-1000);
    CHECK(!memcmp(before,f,sizeof *f) && bytes==0xabcdef01 && restart==0x12345678);
    free(before);k60_owner_abort(&f->fx.session);dispose(f);
}
static void stage_tests(int linked)
{
    Fixture *f=new_case(linked?"linked actual carrier stage1 abort":"captured stage1 abort",linked);
    claim(f);plan_check(f);CHECK(f->fx.session.phase==K60OwnerClaimed);k60_owner_abort(&f->fx.session);
    CHECK(!f->init_calls && !f->auth_calls && !f->shutdown_calls);dispose(f);
    f=new_case("captured stage2 abort",linked);prepare(f);CHECK(f->fx.session.phase==K60OwnerPrepared);
    CHECK(f->lock_calls==2 && f->unlock_calls==2);k60_owner_abort(&f->fx.session);dispose(f);
    f=new_case("real platform copy/BSS and stage3 abort",linked);start(f);
    CHECK(f->fx.session.phase==K60OwnerStarted && f->init_calls==1 && f->mem_calls==1 && f->auth_calls==1);
    CHECK(f->firmware_maps>24 && f->sync_calls==f->firmware_maps);
    k60_owner_abort(&f->fx.session);CHECK(!strcmp(f->cleanup,"STMURE"));dispose(f);
    f=new_case("real remote-ready discovery and stage4 abort",linked);start(f);
    fx_put(&f->fx,f->fx.remote_offset+36,0);f->ready_after_delay=3;
    CHECK(!k60_owner_build_handoff(&f->fx.session,&f->fx.plan));
    CHECK(f->fx.session.phase==K60OwnerBuilt && f->delay_calls==3 && f->fx.session.lease.flags==15);
    CHECK(f->lock_calls==f->unlock_calls && !f->locked);k60_owner_abort(&f->fx.session);dispose(f);
}
static void pas_failures(void)
{
    for(unsigned n=0;n<4;n++) {
        Fixture *f=new_case("pre-AUTH INIT/MEM/map/sync failure safely releases every acquisition",0);prepare(f);destination(f);
        if(n==0)f->init_rc=ERROR;else if(n==1)f->mem_rc=ERROR;
        else if(n==2)f->fail_map_on=3;else f->fail_sync_on=1;
        CHECK(k60_owner_auth_and_start(&f->fx.session)==-1000);
        CHECK(!f->auth_calls && !f->shutdown_calls && f->firmware_maps==f->firmware_unmaps);dispose(f);
    }
    Fixture *f=new_case("AUTH failure shuts down then unmaps/closes/releases",0);prepare(f);destination(f);f->auth_rc=ERROR;
    CHECK(k60_owner_auth_and_start(&f->fx.session)==-1000);
    CHECK(f->auth_calls==1 && f->shutdown_calls==1 && !strcmp(f->cleanup,"STMURE"));dispose(f);
    f=new_case("ready timeout is bounded and safely aborts running owner",0);start(f);
    fx_put(&f->fx,f->fx.remote_offset+36,0);
    CHECK(k60_owner_build_handoff(&f->fx.session,&f->fx.plan)==K60PublishNotReady);
    CHECK(f->delay_calls==999 && f->lock_calls==1002 && f->unlock_calls==1002);
    CHECK(f->shutdown_calls==1);dispose(f);
    f=new_case("ready lock failure releases without delay or held TCSR",0);start(f);f->fail_lock_on=3;
    CHECK(k60_owner_build_handoff(&f->fx.session,&f->fx.plan)==K60PublishNotReady);
    CHECK(!f->delay_calls && f->lock_calls==3 && f->unlock_calls==2);dispose(f);
}
static void poisoned(void)
{
    Fixture *f=new_case("successful SHUTDOWN without independent stopped proof poisons and retains",0);
    prepare(f);destination(f);f->auth_rc=ERROR;f->stop_after_shutdown=0;
    CHECK(k60_owner_auth_and_start(&f->fx.session)==-1000);
    K60OwnerSession *s=&f->fx.session;K60AdspPlatform *p=&f->platform;
    CHECK(s->phase==K60OwnerPoisoned && fx_zero(&s->lease,sizeof s->lease));
    CHECK(s->reserved && s->resources_held && s->mapped && s->image_open && !s->locked);
    CHECK(p->reserved && p->resources_held && p->image_initialized && p->cookie==f && p->epoch==f->fx.epoch);
    CHECK(p->reader.active==1 && p->reader.opened_image==&s->image && p->smem.handle && p->mutex.handle);
    CHECK(f->shutdown_calls==1 && !f->shutdown_rc && f->stopped_value==0 && !strcmp(f->cleanup,"ST"));
    CHECK(!f->unmap_shared && !f->unmap_mutex && !f->resources_releases && !f->release_calls);
    k60_owner_abort(s);CHECK(f->shutdown_calls==1 && p->reader.active==1 && !strcmp(f->cleanup,"ST"));
    const uint8_t *bytes=NULL;size_t n=0;CHECK(!s->image.piece(s->image.context,10,&bytes,&n));
    CHECK(n==720 && !memcmp(bytes,part("adsp.b10")->data,n));
    CHECK(pinned_count<sizeof pinned/sizeof *pinned);pinned[pinned_count++]=f;
}
static void installation(void)
{
    scenario("native services absent install is idempotent but acquire remains unavailable");
    CHECK(k60_adsp_platform_install()==0);CHECK(k60_adsp_platform_install()==1);
    K60AdspOwnerLease l;memset(&l,0xa5,sizeof l);
    OwnerFixture *f=allocate(sizeof *f);fx_case(f,fx_name);
    CHECK(k60_adsp_owner_acquire(&f->config,&l)==-1000);CHECK(fx_zero(&l,sizeof l));
    CHECK(k60_adsp_platform_install()==1);free(f);
}
int main(int argc,char **argv)
{
    fx_name="usage";CHECK(argc==2 || argc==3);load_capture(argv[1],argc==3?argv[2]:NULL);
    complete_ops();availability_tests();acquisition_tests();direct_guards();stage_tests(0);pas_failures();poisoned();
#ifdef K60_ADSP_PLATFORM_TEST_LINKED
    stage_tests(1);
#endif
    installation();
    printf("ASSERT platform captured: PASS MDT=5404 segments=24 COPY=23494284 BSS=25925684 gaps=1960256\n");
    printf("ASSERT platform b10: PASS link=0x86e0b2c0 physical=0xa080b2c0 COPY=720 ZERO=2672 sentinels intact; no b24 callback\n");
    printf("ASSERT platform rollback: PASS second-map rollback, AUTH shutdown/unmap/close/release, independent stopped proof, Poisoned retention\n");
    printf("ASSERT platform guards: PASS all locked non-unlock callbacks have no service/state/output effects; ready config pinned\n");
    printf("TESTS OK adsp-platform: %u scenarios; %s carrier; real C ops and stages; fake low-level services only\n",cases,
#ifdef K60_ADSP_PLATFORM_TEST_LINKED
        "actual linked"
#else
        "absent linked plus explicit captured"
#endif
    );
    return 0;
}
