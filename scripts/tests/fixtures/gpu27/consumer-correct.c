/* The shape the gate allows while the document says index+1. */
static void good_pick(struct kept_panel *db, const struct pong_scanout_frame *frame)
{
    db[frame.target - 1].phys = 0;
}
