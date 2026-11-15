/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AdspImageReader.h"
#include <string.h>
#if defined(__APPLE__)
#define WEAK_DATA __attribute__((weak_import))
#else
#define WEAK_DATA __attribute__((weak))
#endif
extern const uint8_t k60_adsp_blob[] WEAK_DATA;
extern const uint64_t k60_adsp_blob_len WEAK_DATA;
enum { MODE_BLOB=1, MODE_FAT=2 };
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (uint16_t)p[1]<<8); }
static uint32_t rd32(const uint8_t *p) { return rd16(p) | (uint32_t)rd16(p+2)<<16; }
static int fits(uint64_t at,uint64_t n,uint64_t size) { return at<=size && n<=size-at; }
static uint64_t pad8(uint64_t n) { return (n+7u)&~UINT64_C(7); }
static int memory_ok(const void *p,size_t n) { return p && n && (uintptr_t)p<=UINTPTR_MAX-n; }
static int overlap(const void *a,size_t n,const void *b,size_t m)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if (!n || !m) return 0;
    if (x>UINTPTR_MAX-n || y>UINTPTR_MAX-m) return 1;
    return x<y+m && y<x+n;
}
static int canonical(const uint8_t *p,size_t n)
{
    return n==8 && !memcmp(p,"adsp.",5) && (!memcmp(p+5,"mdt",3) ||
        (p[5]=='b' && p[6]>='0' && p[6]<='9' && p[7]>='0' && p[7]<='9'));
}
static const char *part_name(const char *p)
{
    if (!p) return 0;
    size_t n=0; while(n<9 && p[n]) ++n;
    if ((n==3 && !memcmp(p,"mdt",3)) || (n==4 && !memcmp(p,"adsp",4))) return "adsp.mdt";
    return n==8 && canonical((const uint8_t *)p,n) ? p : 0;
}
static const uint8_t *ent(const uint8_t *p,uint32_t i) { return p+8u+(size_t)i*10u; }
static int validate_blob(const uint8_t *p,size_t n)
{
    if (!memory_ok(p,n) || n<8 || n>UINT32_MAX || memcmp(p,"K60A",4)) return -7;
    uint32_t count=rd32(p+4); uint64_t names=8u+(uint64_t)count*10u;
    if (!count || count>K60_ADSP_BLOB_MAX_ENTRIES || names>n) return -7;
    uint64_t cursor=names;
    for(uint32_t i=0;i<count;++i) {
        uint16_t len=rd16(ent(p,i));
        if (!fits(cursor,len,n) || !canonical(p+cursor,len) || !rd32(ent(p,i)+2)) return -7;
        uint64_t previous=names;
        for(uint32_t j=0;j<i;++j) {
            uint16_t pn=rd16(ent(p,j));
            if (len==pn && !memcmp(p+previous,p+cursor,len)) return -7;
            previous+=pn;
        }
        cursor+=len;
    }
    uint64_t body=pad8(cursor);
    if (body>n) return -7;
    for(uint64_t j=cursor;j<body;++j) if(p[j]) return -7;
    for(uint32_t i=0;i<count;++i) {
        const uint8_t *e=ent(p,i); uint32_t size=rd32(e+2),off=rd32(e+6);
        uint64_t end=(uint64_t)off+size,padded=pad8(end);
        if ((off&7u) || off!=body || !fits(off,size,n) || padded>n) return -7;
        for(uint64_t j=end;j<padded;++j) if(p[j]) return -7;
        body=padded;
    }
    return body==n ? 0 : -7;
}
static int blob_find(const K60AdspReader *r,const char *name,const uint8_t **p,size_t *n)
{
    int rc=validate_blob(r->base,r->bytes); if(rc) return rc;
    uint32_t count=rd32(r->base+4); size_t at=8u+(size_t)count*10u;
    for(uint32_t i=0;i<count;++i) {
        const uint8_t *e=ent(r->base,i); uint16_t len=rd16(e);
        if (!memcmp(r->base+at,name,len)) { *p=r->base+rd32(e+6);*n=rd32(e+2);return 0; }
        at+=len;
    }
    return -6;
}
static int validate_fat(const uint8_t *p,size_t n,K60FatVolume *v)
{
    if (!memory_ok(p,n) || n<1024 || p[510]!=0x55 || p[511]!=0xaa) return -7;
    uint32_t bps=rd16(p+11),spc=p[13],res=rd16(p+14),fats=p[16];
    uint32_t fs=rd32(p+36),total=rd32(p+32),root=rd32(p+44);
    if ((bps!=512 && bps!=1024 && bps!=2048 && bps!=4096) || !spc ||
        (spc&(spc-1u)) || spc>128 || !res || !fats || fats>2 || !fs || !total ||
        rd16(p+17) || rd16(p+19) || rd16(p+22) || rd16(p+42) ||
        ((rd16(p+40)&0x80u) && (rd16(p+40)&15u))) return -7;
    uint64_t data=(uint64_t)res+(uint64_t)fats*fs,disk=(uint64_t)total*bps;
    uint64_t clusters=data<total ? (total-data)/spc : 0;
    if (!clusters || clusters>0x0fffffedu || root<2 || root>=clusters+2 ||
        disk>n || disk>UINT32_MAX || (uint64_t)fs*bps/4u<clusters+2u) return -7;
    /* Legacy parser is called only after every arithmetic/address bound above. */
    return k60_fat_open(p,(size_t)disk,v) ? -7 : 0;
}
static int fat_next(const K60AdspReader *r,uint32_t c,uint32_t *next,int *end)
{
    const K60FatVolume *v=&r->fat;
    uint64_t at=(uint64_t)v->reserved_sectors*v->bytes_per_sector+(uint64_t)c*4u;
    if (c<2 || c>=v->clusters+2u || !fits((uint64_t)c*4u,4,(uint64_t)v->fat_sectors*v->bytes_per_sector) ||
        !fits(at,4,r->bytes)) return -7;
    uint32_t x=rd32(r->base+at)&0x0fffffffu;
    if(x>=0x0ffffff8u) { *next=x;*end=1;return 0; }
    if(x<2 || x>=v->clusters+2u) return -7;
    *next=x;*end=0;return 0;
}
static int cluster_at(const K60AdspReader *r,uint32_t c,uint64_t *at)
{
    const K60FatVolume *v=&r->fat;
    if(c<2 || c>=v->clusters+2u) return -7;
    *at=(uint64_t)v->data_start*v->bytes_per_sector+(uint64_t)(c-2u)*v->cluster_bytes;
    return fits(*at,v->cluster_bytes,r->bytes) ? 0 : -7;
}
static int match83(const uint8_t *e,const char *name)
{
    /* Compare base and extension separately: ADSPB00 is not ADSP.B00. */
    uint8_t want[11]={' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' '};
    unsigned base=0,ext=0;int dot=0;
    for(unsigned i=0;name[i] && i<12;++i) {
        char c=name[i];
        if(c=='.') {if(dot)return 0;dot=1;continue;}
        if(c>='a' && c<='z')c=(char)(c-32);
        if(!dot) {if(base==8)return 0;want[base++]=(uint8_t)c;}
        else {if(ext==3)return 0;want[8+ext++]=(uint8_t)c;}
    }
    for(unsigned i=0;i<11;++i) {
        uint8_t c=e[i];if(c>='a'&&c<='z')c=(uint8_t)(c-32);
        if(c!=want[i])return 0;
    }
    return base!=0;
}
typedef struct { uint32_t cluster,size; int directory; } File;
static int dir_find(const K60AdspReader *r,uint32_t c,const char *name,File *f)
{
    /* A corrupt/cyclic directory cannot turn into an unbounded early-boot walk. */
    for(unsigned steps=0;steps<1024;++steps) {
        uint64_t at;int rc=cluster_at(r,c,&at);if(rc)return rc;
        for(uint32_t i=0;i<r->fat.cluster_bytes;i+=32u) {
            const uint8_t *e=r->base+at+i;
            if(!e[0])return -6;
            if(e[0]==0xe5 || (e[11]&15u)==15u || (e[11]&8u))continue;
            if(match83(e,name)) {
                f->cluster=(uint32_t)rd16(e+20)<<16|rd16(e+26);
                f->size=rd32(e+28);f->directory=(e[11]&16u)!=0;return 0;
            }
        }
        uint32_t next;int end;rc=fat_next(r,c,&next,&end);if(rc)return rc;if(end)return -6;c=next;
    }
    return -7;
}
static int fat_find(const K60AdspReader *r,const char *name,const uint8_t **p,size_t *n)
{
    K60FatVolume check={0};int rc=validate_fat(r->base,r->bytes,&check);
    if(rc || memcmp(&check,&r->fat,sizeof check))return -7;
    File dir,file;rc=dir_find(r,r->fat.root_cluster,"ADSP",&dir);if(rc)return rc;
    if(!dir.directory)return -7;
    rc=dir_find(r,dir.cluster,name,&file);if(rc)return rc;
    if(file.directory || !file.size)return -7;
    uint64_t at;rc=cluster_at(r,file.cluster,&at);if(rc)return rc;
    uint64_t count=((uint64_t)file.size+r->fat.cluster_bytes-1u)/r->fat.cluster_bytes;
    if(count>r->fat.clusters)return -7;
    uint32_t c=file.cluster;
    for(uint64_t i=0;i<count;++i) {
        uint32_t next;int end;rc=fat_next(r,c,&next,&end);if(rc)return rc;
        if(i+1u<count) { if(end || next!=c+1u)return -7;c=next; }
        else if(!end)return -7;
    }
    if(!fits(at,file.size,r->bytes))return -7;
    *p=r->base+at;*n=file.size;return 0;
}
int k60_adsp_reader_blob(K60AdspReader *r,const void *base,size_t bytes)
{
    if(!r || r->mode || overlap(r,sizeof *r,base,bytes))return -1;
    if(!base || !bytes)return -6;
    int rc=validate_blob(base,bytes);if(rc)return rc;
    K60AdspReader t={0};t.base=base;t.bytes=bytes;t.mode=MODE_BLOB;*r=t;return 0;
}
int k60_adsp_reader_linked(K60AdspReader *r)
{
    if(!(uintptr_t)k60_adsp_blob || !(uintptr_t)&k60_adsp_blob_len)return -6;
    uint64_t n=k60_adsp_blob_len;
    if((uint64_t)(size_t)n!=n)return -7;
    return k60_adsp_reader_blob(r,k60_adsp_blob,(size_t)n);
}
int k60_adsp_reader_fat(K60AdspReader *r,const void *base,size_t bytes)
{
    if(!r || r->mode || overlap(r,sizeof *r,base,bytes))return -1;
    if(!base || !bytes)return -6;
    K60FatVolume v={0};int rc=validate_fat(base,bytes,&v);if(rc)return rc;
    K60AdspReader t={0};t.base=base;t.bytes=(size_t)v.total_sectors*v.bytes_per_sector;
    t.fat=v;t.mode=MODE_FAT;*r=t;return 0;
}
static int locate(K60AdspReader *r,const char *part,const uint8_t **p,size_t *n)
{
    const char *name=part_name(part);if(!r || !name)return -1;
    if(r->mode==MODE_BLOB)return blob_find(r,name,p,n);
    if(r->mode==MODE_FAT)return fat_find(r,name,p,n);
    return -6;
}
int k60_adsp_reader_borrow(K60AdspReader *r,const char *part,const uint8_t **p,size_t *n)
{
    if(!r || !p || !n || overlap(p,sizeof *p,n,sizeof *n) ||
        overlap(p,sizeof *p,r,sizeof *r) || overlap(n,sizeof *n,r,sizeof *r) ||
        overlap(p,sizeof *p,r->base,r->bytes) || overlap(n,sizeof *n,r->base,r->bytes))return -1;
    const uint8_t *data;size_t bytes;int rc=locate(r,part,&data,&bytes);if(rc)return rc;
    *p=data;*n=bytes;return 0;
}
int k60_adsp_reader_read(K60AdspReader *r,const char *part,void *dst,uint32_t bytes)
{
    if(!r || (!dst && bytes))return -1;
    const uint8_t *p;size_t n;int rc=locate(r,part,&p,&n);if(rc)return rc;
    if(n!=bytes)return -5;
    if(overlap(dst,bytes,r->base,r->bytes) || overlap(dst,bytes,r,sizeof *r))return -1;
    /* Byte copy handles b10's non-page-aligned destination, never rounds a part. */
    for(uint32_t i=0;i<bytes;++i)((uint8_t *)dst)[i]=p[i];
    return 0;
}
int k60_adsp_read(const char *part,void *dst,uint32_t bytes)
{
    K60AdspReader r={0};int rc=k60_adsp_reader_linked(&r);
    return rc?rc:k60_adsp_reader_read(&r,part,dst,bytes);
}
int k60_adsp_image_segment(const K60OwnerImage *image,const K60AdspMdtSegment *s,const uint8_t **p,size_t *n)
{
    if(!image || !s || !p || !n)return -1;
    const uint8_t *data=0;size_t bytes=0;
    if(s->copy_bytes) {
        if(s->source_is_piece) {
            if(!image->piece)return -6;
            int rc=image->piece(image->context,s->index,&data,&bytes);if(rc)return rc;
            if(!data || bytes!=s->copy_bytes)return -5;
            if(!memory_ok(data,bytes))return -7;
        } else {
            if(!memory_ok(image->mdt,image->bytes) ||
                !fits(s->file_offset,s->copy_bytes,image->bytes))return -7;
            data=image->mdt+s->file_offset;bytes=s->copy_bytes;
        }
    }
    *p=data;*n=bytes;return 0;
}
static int owner_piece(void *ctx,uint32_t i,const uint8_t **p,size_t *n)
{
    K60AdspOwnerReader *o=ctx;char part[9]="adsp.b00";
    if(!o || __atomic_load_n(&o->active,__ATOMIC_ACQUIRE)!=1u)return -6;
    if(i>99u)return -7;
    part[6]=(char)('0'+i/10u);part[7]=(char)('0'+i%10u);
    return k60_adsp_reader_borrow(&o->source,part,p,n);
}
int k60_adsp_owner_reader_init(K60AdspOwnerReader *o,const K60AdspReader *r,uint8_t *metadata,size_t cap)
{
    if(!o || !r || !r->mode || o->active || o->source.mode || !memory_ok(metadata,cap) ||
        overlap(o,sizeof *o,r,sizeof *r) || overlap(o,sizeof *o,r->base,r->bytes) ||
        overlap(metadata,cap,r->base,r->bytes) || overlap(metadata,cap,o,sizeof *o) ||
        overlap(metadata,cap,r,sizeof *r))return -1;
    K60AdspOwnerReader t={0};t.source=*r;t.metadata=metadata;t.capacity=cap;*o=t;return 0;
}
int k60_adsp_owner_image_open(void *context,K60OwnerImage *image)
{
    K60AdspOwnerReader *o=context;
    if(!o || !image || !o->source.mode || overlap(image,sizeof *image,o,sizeof *o) ||
        overlap(image,sizeof *image,o->source.base,o->source.bytes) ||
        overlap(image,sizeof *image,o->metadata,o->capacity) ||
        !__sync_bool_compare_and_swap(&o->active,0u,2u))return -1000;
    const uint8_t *p;size_t n;int rc=k60_adsp_reader_borrow(&o->source,"adsp.mdt",&p,&n);
    if(rc) {__atomic_store_n(&o->active,0u,__ATOMIC_RELEASE);return -1000;}
    K60OwnerImage t={0};t.mdt=p;t.bytes=n;t.piece=owner_piece;t.context=o;t.handle=o;
    t.metadata=o->metadata;t.metadata_capacity=o->capacity;
    o->opened_image=image;*image=t;__atomic_store_n(&o->active,1u,__ATOMIC_RELEASE);return 0;
}
void k60_adsp_owner_image_close(void *context,K60OwnerImage *image)
{
    K60AdspOwnerReader *o=context;
    if(!o || !image || !__sync_bool_compare_and_swap(&o->active,1u,2u))return;
    if(o->opened_image!=image || image->handle!=o) {
        __atomic_store_n(&o->active,1u,__ATOMIC_RELEASE);return;
    }
    K60OwnerImage zero={0};*image=zero;o->opened_image=0;
    __atomic_store_n(&o->active,0u,__ATOMIC_RELEASE);
}
