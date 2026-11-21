/* Counter-example: the convention is index+1, this consumer forgets the -1.
   db[frame.target] compiles, reads like "the buffer the kernel named", and is
   off by one - with target==1 it scans db[1] instead of db[0]. */
static void wrong_pick(struct kept_panel *db, const struct pong_scanout_frame *frame)
{
    db[frame.target].phys = 0;
}
