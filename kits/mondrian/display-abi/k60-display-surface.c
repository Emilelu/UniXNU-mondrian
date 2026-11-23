/* K60 minimal display surface group.
 *
 * The iPadOS 24A446 fixture was enumerated from a kernelcache whose IOMobileGraphicsFamily
 * carried a surface helper class.  Our 24A446 kernelcache does not: the same slot addresses
 * land in IOThunderboltFamily (docs/research/ios27/GOP-FRAMEBUFFER-MINIMAL.md 10.1).
 * The generated bindings still own the public symbol names; their .original targets point at
 * the k60_surface_* functions below.  We hand out one small descriptor of our own and every
 * accessor returns a consistent value.  No IOMemoryDescriptor is produced, so the scanout
 * path rejects the transfer with kIOReturnNotReady instead of touching memory it does not own.
 * Console text output does not depend on this group.
 */
typedef unsigned int u32;
typedef unsigned long long u64;

extern void *IOMalloc(unsigned long size);

#define K60_SURFACE_MAGIC 0x4b36305355524631ULL /* K60SURF1 */

struct k60_surface {
    u64 magic;
    u64 allocation;
    u64 stride;
    u32 width;
    u32 height;
    u32 format;
    u32 planes;
};

static struct k60_surface *k60_surface_of(void *object)
{
    struct k60_surface *surface = (struct k60_surface *)object;
    if (!surface || surface->magic != K60_SURFACE_MAGIC)
        return 0;
    return surface;
}

void *native_legacy_default_surface_create(void *root, u32 width, u32 height)
{
    struct k60_surface *surface;
    (void)root;
    if (!width || !height)
        return 0;
    surface = (struct k60_surface *)IOMalloc(sizeof(*surface));
    if (!surface)
        return 0;
    surface->magic = K60_SURFACE_MAGIC;
    surface->width = width;
    surface->height = height;
    surface->stride = (u64)width * 4;
    surface->allocation = surface->stride * height;
    surface->format = 1; /* BGRA8888 */
    surface->planes = 1;
    return surface;
}

void *k60_surface_descriptor(void *object) { (void)object; return 0; }

u64 k60_surface_width(void *object)
{
    struct k60_surface *s = k60_surface_of(object);
    return s ? s->width : 0;
}

u64 k60_surface_height(void *object)
{
    struct k60_surface *s = k60_surface_of(object);
    return s ? s->height : 0;
}

u64 k60_surface_stride(void *object)
{
    struct k60_surface *s = k60_surface_of(object);
    return s ? s->stride : 0;
}

u64 k60_surface_allocation(void *object)
{
    struct k60_surface *s = k60_surface_of(object);
    return s ? s->allocation : 0;
}

u32 k60_surface_format(void *object)
{
    struct k60_surface *s = k60_surface_of(object);
    return s ? s->format : 0;
}

u32 k60_surface_planes(void *object)
{
    struct k60_surface *s = k60_surface_of(object);
    return s ? s->planes : 0;
}

void native_legacy_surface_rejected(u64 a, u64 b, u32 c, u32 d, u64 e, u64 f, u64 g)
{
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g;
}

/* __ZN25IOMobileFramebufferLegacy25create_default_fb_surfaceEv */
void *k60_create_default_fb_surface(void *self)
    __asm__("__ZN25IOMobileFramebufferLegacy25create_default_fb_surfaceEv");
void *k60_create_default_fb_surface(void *self)
{
    (void)self;
    return 0;
}
