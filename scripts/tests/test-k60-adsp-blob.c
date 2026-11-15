/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors.
 * Host-only captured-image regression. No firmware, assembly, or device output.
 * argv[1] is the captured ADSP directory; argv[2], if present, is the
 * generator's dumped K60A binary for byte-for-byte comparison.
 */
#include <dirent.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "K60AdspImageReader.h"

#define PARTS 26u
#define LIMIT 64u
#define GUARD 32u
#define RAW_TOTAL UINT64_C(23505092)
#define BLOB_TOTAL UINT64_C(23506184)
#define REGION_BASE UINT64_C(0x9fd00000)
#define REGION_BYTES UINT64_C(0x03100000)
#define PLAN_SPAN UINT64_C(51380224)
static unsigned checks, malformed_bad, policy_bad, inventory_bad;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)

typedef struct { char name[9]; uint32_t bytes; uint8_t *data; } Part;
typedef struct { uint8_t *data; size_t bytes; } Blob;
typedef struct {
    unsigned count;
    uint64_t record[LIMIT], name[LIMIT], offset[LIMIT], size[LIMIT];
    uint64_t name_end, first_body, cursor;
} Layout;
static const uint32_t expected[PARTS] = {
    5404,884,6952,3216484,25720,34632,710336,220,4892,2306824,
    237576,720,9960,131232,83220,3167652,108732,280,185008,
    11511192,503816,1936,201084,103736,942080,4520
};
static uint16_t get16(const uint8_t *p)
{ return (uint16_t)((uint16_t)p[0] | (uint16_t)p[1] << 8); }
static uint32_t get32(const uint8_t *p)
{ return (uint32_t)get16(p) | (uint32_t)get16(p+2) << 16; }
static uint64_t get64(const uint8_t *p)
{ return (uint64_t)get32(p) | (uint64_t)get32(p+4) << 32; }
static void put16(uint8_t *p,uint16_t v)
{ p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t *p,uint32_t v)
{ put16(p,(uint16_t)v); put16(p+2,(uint16_t)(v>>16)); }
static void put64(uint8_t *p,uint64_t v)
{ put32(p,(uint32_t)v); put32(p+4,(uint32_t)(v>>32)); }
static int plus(uint64_t a,uint64_t b,uint64_t *out)
{ if (a>UINT64_MAX-b) return 0; *out=a+b; return 1; }
static int align8(uint64_t n,uint64_t *out)
{ uint64_t v; if (!plus(n,7,&v)) return 0; *out=v&~UINT64_C(7); return 1; }
static int inside(uint64_t at,uint64_t n,uint64_t total)
{ return at<=total && n<=total-at; }
static int filled(const uint8_t *p,size_t n,uint8_t byte)
{ for (size_t i=0;i<n;++i) if (p[i]!=byte) return 0; return 1; }
static int zero_pad(const uint8_t *p,uint64_t a,uint64_t b,uint64_t total)
{ return b>=a && inside(a,b-a,total) && filled(p+(size_t)a,(size_t)(b-a),0); }
static int valid_name(const uint8_t *p,size_t n)
{
    return n==8 && !memcmp(p,"adsp.",5) &&
        (!memcmp(p+5,"mdt",3) || (p[5]=='b' && p[6]>='0' && p[6]<='9' &&
                                    p[7]>='0' && p[7]<='9'));
}
static void names(Part *parts)
{
    memset(parts,0,sizeof(*parts)*PARTS);
    memcpy(parts[0].name,"adsp.mdt",9);
    for (unsigned i=1;i<PARTS;++i) {
        unsigned index=i==25 ? 25 : i-1;
        memcpy(parts[i].name,"adsp.b00",9);
        parts[i].name[6]=(char)('0'+index/10);
        parts[i].name[7]=(char)('0'+index%10);
    }
}
/* Inventory is independent of directory order; sidecars are ignored, not read. */
static int inventory_ok(const Part *parts,char entries[][256],unsigned count)
{
    unsigned seen[PARTS]={0};
    for (unsigned j=0;j<count;++j) {
        const char *name=entries[j];
        if (!strcmp(name,"adspr.jsn") || !strcmp(name,"adspua.jsn")) continue;
        unsigned i=0;
        while (i<PARTS && strcmp(parts[i].name,name)) ++i;
        if (i==PARTS || seen[i]++) return 0;
    }
    for (unsigned i=0;i<PARTS;++i) if (seen[i]!=1) return 0;
    return 1;
}
static void test_inventory(const Part *parts)
{
    char entries[PARTS+2][256]={{0}};
    for (unsigned i=0;i<PARTS;++i) strcpy(entries[i],parts[i].name);
    CHECK(inventory_ok(parts,entries,PARTS));
    CHECK(!inventory_ok(parts,entries,PARTS-1)); ++inventory_bad;
    strcpy(entries[PARTS],"adsp.b24");
    CHECK(!inventory_ok(parts,entries,PARTS+1)); ++inventory_bad;
    strcpy(entries[PARTS],"adsp.b26");
    CHECK(!inventory_ok(parts,entries,PARTS+1)); ++inventory_bad;
    strcpy(entries[PARTS],"adsp.mdt");
    CHECK(!inventory_ok(parts,entries,PARTS+1)); ++inventory_bad;
    strcpy(entries[PARTS],"adspr.jsn"); strcpy(entries[PARTS+1],"adspua.jsn");
    CHECK(inventory_ok(parts,entries,PARTS+2));
}
static void load_parts(const char *directory,Part *parts)
{
    DIR *dir=opendir(directory); CHECK(dir!=NULL);
    char entries[LIMIT][256]={{0}}; unsigned count=0; struct dirent *e;
    while ((e=readdir(dir))) {
        if (!strcmp(e->d_name,".") || !strcmp(e->d_name,"..")) continue;
        CHECK(count<LIMIT && strlen(e->d_name)<sizeof entries[0]);
        strcpy(entries[count++],e->d_name);
    }
    CHECK(closedir(dir)==0); CHECK(inventory_ok(parts,entries,count));
    uint64_t total=0;
    for (unsigned i=0;i<PARTS;++i) {
        char path[4096]; struct stat st;
        int len=snprintf(path,sizeof path,"%s/%s",directory,parts[i].name);
        CHECK(len>0 && (size_t)len<sizeof path);
        CHECK(stat(path,&st)==0 && S_ISREG(st.st_mode));
        CHECK(st.st_size==(long long)expected[i]);
        parts[i].bytes=expected[i]; parts[i].data=malloc(parts[i].bytes);
        CHECK(parts[i].data!=NULL); FILE *f=fopen(path,"rb"); CHECK(f!=NULL);
        CHECK(fread(parts[i].data,1,parts[i].bytes,f)==parts[i].bytes);
        CHECK(fgetc(f)==EOF && !ferror(f)); CHECK(fclose(f)==0);
        total+=parts[i].bytes;
    }
    CHECK(total==RAW_TOTAL);
}
/* Independent sequential production-ABI validator; does not call reader internals. */
static int inspect_blob(const uint8_t *p,size_t total,Layout *result)
{
    Layout v={0}; uint64_t cursor=12;
    if (!p || total<12 || total>UINT32_MAX || memcmp(p,"K60A",4) || get32(p+8)) return -7;
    v.count=get32(p+4); if (!v.count || v.count>LIMIT) return -7;
    for (unsigned i=0;i<v.count;++i) {
        uint64_t after,name_at,name_end,body_at,body_end,next;
        if (!inside(cursor,24,total)) return -7;
        const uint8_t *r=p+(size_t)cursor;
        uint32_t name_len=get32(r),mode=get32(r+4);
        uint64_t size=get64(r+8),packed=get64(r+16);
        if (mode!=0644 || packed!=size) return -8;
        if (name_len!=9 || !size || !plus(cursor,24,&after) ||
            !align8(after,&name_at) || !zero_pad(p,after,name_at,total) ||
            !inside(name_at,name_len,total)) return -7;
        const uint8_t *name=p+(size_t)name_at;
        if (name[8] || !valid_name(name,8) || memchr(name,0,8)) return -7;
        for (unsigned j=0;j<i;++j)
            if (!memcmp(p+(size_t)v.name[j],name,9)) return -7;
        if (!plus(name_at,name_len,&name_end) || !align8(name_end,&body_at) ||
            !zero_pad(p,name_end,body_at,total) || !inside(body_at,size,total) ||
            !plus(body_at,size,&body_end) || !align8(body_end,&next) ||
            !zero_pad(p,body_end,next,total)) return -7;
        for (unsigned j=0;j<i;++j) {
            uint64_t previous;
            if (!plus(v.offset[j],v.size[j],&previous) ||
                (body_at<previous && v.offset[j]<body_end)) return -7;
        }
        v.record[i]=cursor; v.name[i]=name_at; v.offset[i]=body_at; v.size[i]=size;
        if (!i) { v.first_body=body_at; v.name_end=name_end; }
        cursor=next;
    }
    v.cursor=cursor; if (cursor!=total) return -7;
    if (result) *result=v;
    return 0;
}
static Blob make_blob(const Part *parts)
{
    uint64_t cursor=12,record[PARTS],name[PARTS],body[PARTS];
    for (unsigned i=0;i<PARTS;++i) {
        record[i]=cursor; CHECK(plus(cursor,24,&cursor)); CHECK(align8(cursor,&cursor));
        name[i]=cursor; CHECK(plus(cursor,9,&cursor)); CHECK(align8(cursor,&cursor));
        body[i]=cursor; CHECK(plus(cursor,parts[i].bytes,&cursor)); CHECK(align8(cursor,&cursor));
    }
    CHECK(cursor==BLOB_TOTAL && cursor<=SIZE_MAX);
    Blob b={calloc(1,(size_t)cursor),(size_t)cursor}; CHECK(b.data!=NULL);
    memcpy(b.data,"K60A",4); put32(b.data+4,PARTS); put32(b.data+8,0);
    for (unsigned i=0;i<PARTS;++i) {
        uint8_t *e=b.data+(size_t)record[i];
        put32(e,9); put32(e+4,0644); put64(e+8,parts[i].bytes); put64(e+16,parts[i].bytes);
        memcpy(b.data+(size_t)name[i],parts[i].name,9);
        memcpy(b.data+(size_t)body[i],parts[i].data,parts[i].bytes);
    }
    return b;
}
static Blob read_blob(const char *path)
{
    FILE *f=fopen(path,"rb"); CHECK(f!=NULL);
    CHECK(fseek(f,0,SEEK_END)==0); long end=ftell(f);
    CHECK(end>0 && fseek(f,0,SEEK_SET)==0);
    Blob b={(uint8_t *)malloc((size_t)end),(size_t)end}; CHECK(b.data!=NULL);
    CHECK(fread(b.data,1,b.bytes,f)==b.bytes && !ferror(f)); CHECK(fclose(f)==0);
    return b;
}
static void exact_layout(const Blob *b,const Layout *v,const Part *parts)
{
    CHECK(v->count==PARTS && v->cursor==b->bytes);
    for (unsigned i=0;i<PARTS;++i) {
        CHECK(v->size[i]==parts[i].bytes);
        CHECK(!memcmp(b->data+(size_t)v->name[i],parts[i].name,9));
        CHECK(!memcmp(b->data+(size_t)v->offset[i],parts[i].data,parts[i].bytes));
    }
}
static void unchanged_error(K60AdspReader *r,const char *part,int expected_rc)
{
    uint8_t sentinel=0xa7,dst[32]; memset(dst,0x5a,sizeof dst);
    const uint8_t *p=&sentinel; size_t n=987;
    CHECK(k60_adsp_reader_borrow(r,part,&p,&n)==expected_rc);
    CHECK(p==&sentinel && n==987);
    CHECK(k60_adsp_reader_read(r,part,dst,sizeof dst)==expected_rc);
    CHECK(filled(dst,sizeof dst,0x5a));
}
static void test_reader(Blob *blob,const Layout *view,const Part *parts,K60AdspReader *reader)
{
    CHECK(k60_adsp_reader_blob(reader,blob->data,blob->bytes)==0);
    for (unsigned i=0;i<PARTS;++i) {
        const uint8_t *p=NULL; size_t n=0;
        CHECK(k60_adsp_reader_borrow(reader,parts[i].name,&p,&n)==0);
        CHECK(n==parts[i].bytes && p==blob->data+(size_t)view->offset[i]);
        CHECK(!memcmp(p,parts[i].data,n));
        uint8_t *dst=malloc(n+2*GUARD); CHECK(dst!=NULL); memset(dst,0x6d,n+2*GUARD);
        CHECK(k60_adsp_reader_read(reader,parts[i].name,dst+GUARD,(uint32_t)n)==0);
        CHECK(!memcmp(dst+GUARD,parts[i].data,n));
        CHECK(filled(dst,GUARD,0x6d) && filled(dst+GUARD+n,GUARD,0x6d));
        memset(dst+GUARD,0xb3,n);
        CHECK(k60_adsp_reader_read(reader,parts[i].name,dst+GUARD,(uint32_t)n-1)==-5);
        CHECK(filled(dst+GUARD,n,0xb3));
        CHECK(k60_adsp_reader_read(reader,parts[i].name,dst+GUARD,(uint32_t)n+1)==-5);
        CHECK(filled(dst+GUARD,n,0xb3));
        CHECK(filled(dst,GUARD,0x6d) && filled(dst+GUARD+n,GUARD,0x6d)); free(dst);
    }
    const char *aliases[]={"mdt","adsp"};
    for (unsigned i=0;i<2;++i) {
        const uint8_t *p=NULL; size_t n=0; uint8_t dst[5404];
        CHECK(k60_adsp_reader_borrow(reader,aliases[i],&p,&n)==0);
        CHECK(n==parts[0].bytes && !memcmp(p,parts[0].data,n));
        CHECK(k60_adsp_reader_read(reader,aliases[i],dst,sizeof dst)==0);
        CHECK(!memcmp(dst,parts[0].data,sizeof dst));
    }
    unchanged_error(reader,"adsp.b24",-6); unchanged_error(reader,"adsp.b99",-6);
    K60AdspReader absent={0}; unchanged_error(&absent,"mdt",-6);
    K60AdspReader before={0}; absent.bytes=123; before=absent;
    CHECK(k60_adsp_reader_blob(&absent,NULL,0)==-6);
    CHECK(!memcmp(&absent,&before,sizeof before));
    uint8_t saved=blob->data[0]; blob->data[0]='X';
    unchanged_error(reader,"adsp.mdt",-7); blob->data[0]=saved;
}
static void reject_malformed(const Blob *b,size_t bytes)
{
    CHECK(inspect_blob(b->data,bytes,NULL)==-7);
    K60AdspReader reader={0},before; reader.bytes=123; before=reader;
    CHECK(k60_adsp_reader_blob(&reader,b->data,bytes)==-7);
    CHECK(!memcmp(&reader,&before,sizeof reader));
    reader.base=b->data; reader.bytes=bytes; reader.mode=1;
    unchanged_error(&reader,"adsp.mdt",-7); ++malformed_bad;
}
static void reject_policy(const Blob *b)
{
    CHECK(inspect_blob(b->data,b->bytes,NULL)==-8);
    K60AdspReader reader={0},before; reader.bytes=123; before=reader;
    CHECK(k60_adsp_reader_blob(&reader,b->data,b->bytes)==-8);
    CHECK(!memcmp(&reader,&before,sizeof reader));
    reader.base=b->data; reader.bytes=b->bytes; reader.mode=1;
    unchanged_error(&reader,"adsp.mdt",-8); ++policy_bad;
}
static void blob_mutations(const Blob *blob,const Layout *v)
{
    Blob b={(uint8_t *)malloc(blob->bytes+8),blob->bytes}; CHECK(b.data!=NULL);
#define BLOB_RESET() memcpy(b.data,blob->data,blob->bytes)
#define BLOB_BAD(statement) do { BLOB_RESET(); statement; reject_malformed(&b,b.bytes); } while (0)
#define BLOB_POLICY(statement) do { BLOB_RESET(); statement; reject_policy(&b); } while (0)
    BLOB_BAD(b.data[0]='X');
    BLOB_BAD(put32(b.data+4,0));
    BLOB_BAD(put32(b.data+4,65));
    BLOB_BAD(put32(b.data+4,UINT32_MAX));
    BLOB_BAD(put32(b.data+8,1));
    BLOB_BAD(put32(b.data+(size_t)v->record[0],0));
    BLOB_BAD(put32(b.data+(size_t)v->record[0],8));
    BLOB_BAD(put32(b.data+(size_t)v->record[0],UINT32_MAX));
    BLOB_BAD(b.data[(size_t)v->name[0]+8]='X');
    BLOB_BAD(b.data[(size_t)v->name[0]]=0);
    BLOB_BAD(b.data[(size_t)v->name[0]+3]=0);
    BLOB_BAD(b.data[(size_t)v->name[0]]='X');
    BLOB_BAD(memcpy(b.data+(size_t)v->name[1],b.data+(size_t)v->name[0],9));
    BLOB_POLICY(put32(b.data+(size_t)v->record[0]+4,0600));
    BLOB_POLICY(put32(b.data+(size_t)v->record[0]+4,0100644));
    BLOB_POLICY(put64(b.data+(size_t)v->record[0]+16,v->size[0]-1));
    BLOB_BAD(put64(b.data+(size_t)v->record[0]+8,0); put64(b.data+(size_t)v->record[0]+16,0));
    BLOB_BAD(put64(b.data+(size_t)v->record[0]+8,UINT64_MAX); put64(b.data+(size_t)v->record[0]+16,UINT64_MAX));
    BLOB_BAD(b.data[(size_t)v->record[0]+24]=1);
    BLOB_BAD(b.data[(size_t)v->name[0]+9]=1);
    BLOB_BAD(b.data[(size_t)(v->offset[0]+v->size[0])]=1);
    BLOB_RESET(); memset(b.data+blob->bytes,0,8); reject_malformed(&b,blob->bytes+8);
    const size_t cuts[]={1,7,8,11,12,35,36,39,40,48,49,55};
    for (unsigned i=0;i<sizeof cuts/sizeof cuts[0];++i) { BLOB_RESET(); reject_malformed(&b,cuts[i]); }
    for (unsigned i=0;i<PARTS;++i) {
        BLOB_RESET(); reject_malformed(&b,(size_t)(v->offset[i]+v->size[i]-1));
        BLOB_RESET(); reject_malformed(&b,(size_t)v->record[i]+23);
    }
    free(b.data);
#undef BLOB_POLICY
#undef BLOB_BAD
#undef BLOB_RESET
}
/* Delegates real plan reads while recording owner-adapter requests. */
typedef struct { K60OwnerImage *image; unsigned calls[100]; } Trace;
static int traced_piece(void *ctx,uint32_t index,const uint8_t **p,size_t *n)
{
    Trace *t=ctx; if (index>=100) return -7;
    ++t->calls[index]; return t->image->piece(t->image->context,index,p,n);
}
/* Direct captured-file buffers bypass blob layout and owner adapter. */
typedef struct { const Part *parts; unsigned calls[100]; } Direct;
static int direct_piece(void *ctx,uint32_t index,const uint8_t **p,size_t *n)
{
    Direct *d=ctx; if (index>=100) return -6;
    ++d->calls[index];
    if (index==24 || index>25) return -6;
    unsigned which=index==25 ? 25 : index+1;
    *p=d->parts[which].data; *n=d->parts[which].bytes; return 0;
}
static void compare_plans(const K60AdspMdtPlan *a,const K60AdspMdtPlan *b)
{
    CHECK(a->headers==b->headers && a->count==b->count);
    CHECK(a->hash_index==b->hash_index && a->relocatable==b->relocatable);
    CHECK(a->prefix_bytes==b->prefix_bytes && a->hash_bytes==b->hash_bytes);
    CHECK(a->link_base==b->link_base && a->span==b->span);
    CHECK(a->region_base==b->region_base && a->region_bytes==b->region_bytes);
    for (unsigned i=0;i<a->count;++i) {
        const K60AdspMdtSegment *x=&a->segment[i],*y=&b->segment[i];
        CHECK(x->index==y->index); CHECK(x->flags==y->flags);
        CHECK(x->file_offset==y->file_offset); CHECK(x->link_address==y->link_address);
        CHECK(x->copy_bytes==y->copy_bytes); CHECK(x->zero_bytes==y->zero_bytes);
        CHECK(x->source_is_piece==y->source_is_piece); CHECK(x->destination==y->destination);
    }
}
static int plan24_ok(const K60AdspMdtPlan *p)
{
    return p->headers==26 && p->count==24 && p->hash_index==25 && p->relocatable==1 &&
        p->prefix_bytes==884 && p->hash_bytes==4520 && p->link_base==UINT64_C(0x86300000);
}
static int copy_totals_ok(uint64_t copy,uint64_t zero,uint64_t gaps)
{
    return copy==UINT64_C(23494284) && zero==UINT64_C(25925684) &&
        gaps==UINT64_C(1960256) && copy+zero+gaps==PLAN_SPAN;
}
static int segment_bytes_ok(const K60AdspMdtSegment *s,const Part *parts,
                            const uint8_t *destination)
{
    uint64_t at=s->destination-REGION_BASE,n=(uint64_t)s->copy_bytes+s->zero_bytes;
    if (s->destination<REGION_BASE || !inside(at,n,PLAN_SPAN)) return 0;
    if (s->copy_bytes) {
        unsigned which=s->index==25 ? 25 : s->index+1;
        if (which>=PARTS || s->copy_bytes!=parts[which].bytes ||
            memcmp(destination+(size_t)at,parts[which].data,s->copy_bytes)) return 0;
    }
    return filled(destination+(size_t)at+s->copy_bytes,s->zero_bytes,0);
}
static int copied_image_ok(const K60AdspMdtPlan *plan,const unsigned *order,
                           const Part *parts,const uint8_t *allocation)
{
    const uint8_t *destination=allocation+GUARD;
    uint64_t copy=0,zero=0,gaps=0,cursor=0;
    if (!filled(allocation,GUARD,0xcc) ||
        !filled(destination+(size_t)PLAN_SPAN,GUARD,0xcc)) return 0;
    for (unsigned k=0;k<plan->count;++k) {
        const K60AdspMdtSegment *s=&plan->segment[order[k]];
        uint64_t at=s->destination-REGION_BASE,n=(uint64_t)s->copy_bytes+s->zero_bytes;
        if (s->destination<REGION_BASE || !inside(at,n,PLAN_SPAN) || at<cursor ||
            !filled(destination+(size_t)cursor,(size_t)(at-cursor),0xcc) ||
            !segment_bytes_ok(s,parts,destination)) return 0;
        gaps+=at-cursor; copy+=s->copy_bytes; zero+=s->zero_bytes; cursor=at+n;
    }
    if (cursor>PLAN_SPAN ||
        !filled(destination+(size_t)cursor,(size_t)(PLAN_SPAN-cursor),0xcc)) return 0;
    return copy_totals_ok(copy,zero,gaps+PLAN_SPAN-cursor);
}
static int segment10_ok(const K60AdspMdtSegment *s,const Part *parts,
                        const uint8_t *destination)
{
    return s->link_address==UINT32_C(0x86e0b2c0) &&
        s->destination==UINT64_C(0xa080b2c0) && s->copy_bytes==720 && s->zero_bytes==2672 &&
        (s->destination&4095)==0x2c0 && segment_bytes_ok(s,parts,destination);
}
static void test_owner(K60AdspReader *reader,const Part *parts)
{
    uint8_t *metadata=malloc(5404+2*GUARD); CHECK(metadata!=NULL);
    memset(metadata,0xd2,5404+2*GUARD);
    K60AdspOwnerReader owner={0}; K60OwnerImage image={0};
    CHECK(k60_adsp_owner_reader_init(&owner,reader,metadata+GUARD,5404)==0);
    CHECK(k60_adsp_owner_image_open(&owner,&image)==0);
    CHECK(image.bytes==5404 && !memcmp(image.mdt,parts[0].data,image.bytes));
    CHECK(image.metadata==metadata+GUARD && image.metadata_capacity==5404);
    Trace trace={0}; trace.image=&image; K60AdspMdtPlan plan;
    CHECK(k60_adsp_mdt_prepare(image.mdt,image.bytes,REGION_BASE,REGION_BYTES,
          traced_piece,&trace,image.metadata,image.metadata_capacity,&plan)==0);
    CHECK(plan24_ok(&plan));
    CHECK(plan.region_base==REGION_BASE && plan.region_bytes==REGION_BYTES && plan.span==PLAN_SPAN);
    CHECK(!memcmp(image.metadata,parts[0].data,5404));
    CHECK(filled(metadata,GUARD,0xd2) && filled(metadata+GUARD+5404,GUARD,0xd2));
    uint8_t *direct_metadata=malloc(5404+2*GUARD); CHECK(direct_metadata!=NULL);
    memset(direct_metadata,0x73,5404+2*GUARD);
    Direct direct={0}; direct.parts=parts; K60AdspMdtPlan direct_plan;
    CHECK(k60_adsp_mdt_prepare(parts[0].data,parts[0].bytes,REGION_BASE,REGION_BYTES,
          direct_piece,&direct,direct_metadata+GUARD,5404,&direct_plan)==0);
    compare_plans(&plan,&direct_plan);
    CHECK(!memcmp(direct_metadata+GUARD,image.metadata,5404));
    CHECK(!memcmp(direct_metadata+GUARD,parts[0].data,5404));
    CHECK(filled(direct_metadata,GUARD,0x73) && filled(direct_metadata+GUARD+5404,GUARD,0x73));
    for (unsigned i=0;i<=25;++i) CHECK(direct.calls[i]==(i>=1 && i<=23 ? 1u : 0u));
    CHECK(direct.calls[24]==0);
    /* Drop the actual pure-BSS PT_LOAD header, then run the production planner. */
    uint8_t bad_mdt[5404],bad_metadata[5404]; K60AdspMdtPlan bad_plan;
    memcpy(bad_mdt,parts[0].data,sizeof bad_mdt); put32(bad_mdt+52+24*32,0);
    Direct bad_direct={0}; bad_direct.parts=parts;
    CHECK(k60_adsp_mdt_prepare(bad_mdt,sizeof bad_mdt,REGION_BASE,REGION_BYTES,
          direct_piece,&bad_direct,bad_metadata,sizeof bad_metadata,&bad_plan)==0);
    CHECK(bad_plan.count==23 && !plan24_ok(&bad_plan));
    uint8_t *allocation=malloc((size_t)PLAN_SPAN+2*GUARD); CHECK(allocation!=NULL);
    memset(allocation,0xcc,(size_t)PLAN_SPAN+2*GUARD); uint8_t *destination=allocation+GUARD;
    uint64_t copy=0,zero=0,cursor=0,gaps=0; unsigned seen10=0,seen24=0;
    K60OwnerImage traced=image; traced.piece=traced_piece; traced.context=&trace;
    /* Address-sort independently; MDT header order is not address order. */
    unsigned order[K60_ADSP_MDT_MAX_HEADERS];
    for (unsigned i=0;i<plan.count;++i) order[i]=i;
    for (unsigned i=0;i<plan.count;++i) for (unsigned j=i+1;j<plan.count;++j)
        if (plan.segment[order[j]].destination<plan.segment[order[i]].destination) {
            unsigned swap=order[i]; order[i]=order[j]; order[j]=swap;
        }
    for (unsigned k=0;k<plan.count;++k) {
        const K60AdspMdtSegment *s=&plan.segment[order[k]];
        uint64_t at=s->destination-REGION_BASE,n=(uint64_t)s->copy_bytes+s->zero_bytes;
        CHECK(s->destination>=REGION_BASE && inside(at,n,PLAN_SPAN) && at>=cursor);
        CHECK(filled(destination+(size_t)cursor,(size_t)(at-cursor),0xcc)); gaps+=at-cursor;
        const uint8_t *source=(const uint8_t *)image.mdt; size_t bytes=123;
        unsigned old24=trace.calls[24];
        CHECK(k60_adsp_image_segment(&traced,s,&source,&bytes)==0);
        CHECK(bytes==s->copy_bytes);
        if (s->copy_bytes) {
            unsigned which=s->index+1; if (s->index==25) which=25;
            CHECK(s->source_is_piece==1 && which<PARTS && parts[which].bytes==bytes);
            CHECK(source!=NULL && !memcmp(source,parts[which].data,bytes));
            memcpy(destination+(size_t)at,source,bytes);
        } else CHECK(source==NULL);
        memset(destination+(size_t)at+s->copy_bytes,0,s->zero_bytes);
        if (s->copy_bytes) CHECK(!memcmp(destination+(size_t)at,source,s->copy_bytes));
        CHECK(filled(destination+(size_t)at+s->copy_bytes,s->zero_bytes,0));
        if (s->index==10) {
            ++seen10; CHECK(segment10_ok(s,parts,destination));
            /* Corrupt both ends of copied data and BSS through the same check. */
            const size_t corrupt[]={0,719,720,3391};
            for (unsigned j=0;j<sizeof corrupt/sizeof corrupt[0];++j) {
                uint8_t *byte=destination+(size_t)at+corrupt[j]; *byte^=1;
                CHECK(!segment10_ok(s,parts,destination)); *byte^=1;
                CHECK(segment10_ok(s,parts,destination));
            }
        }
        if (s->index==24) {
            ++seen24; CHECK(!s->copy_bytes && s->zero_bytes>0);
            CHECK(trace.calls[24]==old24);
        }
        copy+=s->copy_bytes; zero+=s->zero_bytes; cursor=at+n;
    }
    CHECK(cursor<=PLAN_SPAN); gaps+=PLAN_SPAN-cursor;
    CHECK(filled(destination+(size_t)cursor,(size_t)(PLAN_SPAN-cursor),0xcc));
    cursor=0;
    for (unsigned k=0;k<plan.count;++k) {
        const K60AdspMdtSegment *s=&plan.segment[order[k]];
        uint64_t at=s->destination-REGION_BASE;
        CHECK(filled(destination+(size_t)cursor,(size_t)(at-cursor),0xcc));
        cursor=at+s->copy_bytes+s->zero_bytes;
    }
    CHECK(filled(destination+(size_t)cursor,(size_t)(PLAN_SPAN-cursor),0xcc));
    CHECK(filled(allocation,GUARD,0xcc) && filled(destination+(size_t)PLAN_SPAN,GUARD,0xcc));
    CHECK(copy_totals_ok(copy,zero,gaps));
    CHECK(copied_image_ok(&plan,order,parts,allocation));
    unsigned corrupted_copy=0,corrupted_bss=0,corrupted_gap=0; cursor=0;
    for (unsigned k=0;k<plan.count;++k) {
        const K60AdspMdtSegment *s=&plan.segment[order[k]];
        size_t at=(size_t)(s->destination-REGION_BASE);
        if (!corrupted_copy && s->copy_bytes) {
            destination[at]^=1; CHECK(!copied_image_ok(&plan,order,parts,allocation));
            destination[at]^=1; corrupted_copy=1;
        }
        if (!corrupted_bss && s->zero_bytes) {
            destination[at+s->copy_bytes]=1;
            CHECK(!copied_image_ok(&plan,order,parts,allocation));
            destination[at+s->copy_bytes]=0; corrupted_bss=1;
        }
        if (!corrupted_gap && at>cursor) {
            destination[(size_t)cursor]^=1;
            CHECK(!copied_image_ok(&plan,order,parts,allocation));
            destination[(size_t)cursor]^=1; corrupted_gap=1;
        }
        cursor=at+s->copy_bytes+s->zero_bytes;
    }
    CHECK(corrupted_copy && corrupted_bss && corrupted_gap);
    allocation[0]^=1; CHECK(!copied_image_ok(&plan,order,parts,allocation)); allocation[0]^=1;
    destination[(size_t)PLAN_SPAN]^=1;
    CHECK(!copied_image_ok(&plan,order,parts,allocation));
    destination[(size_t)PLAN_SPAN]^=1;
    CHECK(copied_image_ok(&plan,order,parts,allocation));
    CHECK(seen10==1 && seen24==1 && trace.calls[24]==0);
    for (unsigned i=0;i<=25;++i)
        CHECK(trace.calls[i]==(i>=1 && i<=23 ? 2u : 0u));
    printf("ASSERT plan24: headers=26 segments=24 hash=25; negative=mutated-MDT count23 rejected\n");
    printf("ASSERT copy: bytes=%" PRIu64 " BSS=%" PRIu64 "; negative=payload/BSS/gap/guard corruption rejected\n",copy,zero);
    printf("ASSERT b10: link=0x86e0b2c0 dest=0xa080b2c0 bytecopy=720 BSS=2672 sentinels/gaps=OK; negative=payload/BSS corruption rejected\n");
    k60_adsp_owner_image_close(&owner,&image);
    CHECK(owner.active==0 && image.mdt==NULL && image.piece==NULL && image.handle==NULL);
    free(allocation); free(direct_metadata); free(metadata);
}
static int container_ok(const uint8_t *p,size_t bytes)
{
    Layout view;
    return inspect_blob(p,bytes,&view)==0 && bytes==BLOB_TOTAL &&
        view.count==PARTS && view.cursor==BLOB_TOTAL;
}
static void test_container_assertion(const Blob *blob)
{
    CHECK(container_ok(blob->data,blob->bytes));
    uint8_t *bad=(uint8_t *)malloc(blob->bytes); CHECK(bad!=NULL);
    memcpy(bad,blob->data,blob->bytes); put32(bad+4,PARTS+1);
    CHECK(!container_ok(bad,blob->bytes));
    K60AdspReader reader={0}; CHECK(k60_adsp_reader_blob(&reader,bad,blob->bytes)==-7);
    printf("ASSERT container: bytes=%zu count=26; negative=count27 rejected\n",blob->bytes);
    free(bad);
}
static void test_obsolete_flat(void)
{
    /* Minimal old 8-byte-header/10-byte-record specimen; no flat parser/builder. */
    uint8_t old[27]={0}; memcpy(old,"K60A",4); put32(old+4,1);
    put16(old+8,8); put32(old+10,1); put32(old+14,26);
    memcpy(old+18,"adsp.mdt",8); old[26]=0x5a;
    CHECK(inspect_blob(old,sizeof old,NULL)==-7);
    K60AdspReader reader={0},before; reader.bytes=77; before=reader;
    int rc=k60_adsp_reader_blob(&reader,old,sizeof old);
    CHECK(rc==-7 && !memcmp(&reader,&before,sizeof reader));
    printf("ASSERT obsolete-flat: production rc=%d; independent malformed=-7\n",rc);
}
int main(int argc,char **argv)
{
    if (argc!=2 && argc!=3) {
        fprintf(stderr,"usage: %s /mnt/e/k60-work/firmware/adsp [generated-k60a.bin]\n",argv[0]);
        return 2;
    }
    Part parts[PARTS]; names(parts); test_inventory(parts); load_parts(argv[1],parts);
    uint64_t arithmetic=99;
    CHECK(!plus(UINT64_MAX,1,&arithmetic) && arithmetic==99);
    CHECK(!align8(UINT64_MAX,&arithmetic) && arithmetic==99);
    CHECK(!inside(UINT64_MAX,1,UINT64_MAX));
    Blob built=make_blob(parts); Layout built_view;
    CHECK(inspect_blob(built.data,built.bytes,&built_view)==0);
    exact_layout(&built,&built_view,parts);
    CHECK(built_view.first_body==56 && built_view.name_end==49);
    Blob generated={0}; Blob *production=&built; Layout production_view=built_view;
    if (argc==3) {
        generated=read_blob(argv[2]);
        CHECK(generated.bytes==built.bytes && !memcmp(generated.data,built.data,built.bytes));
        CHECK(inspect_blob(generated.data,generated.bytes,&production_view)==0);
        exact_layout(&generated,&production_view,parts); production=&generated;
    }
    K60AdspReader reader={0}; test_reader(production,&production_view,parts,&reader);
    test_owner(&reader,parts);
    test_container_assertion(&built); test_obsolete_flat();
    blob_mutations(&built,&built_view);
    free(generated.data); free(built.data);
    for (unsigned i=0;i<PARTS;++i) free(parts[i].data);
    (void)checks; (void)malformed_bad; (void)policy_bad; (void)inventory_bad;
    return 0;
}
