/* Counter-example for the opposite direction: if the field ever goes back to
   holding a raw index, subtracting one is the mistake, and it fails the same
   way (db[-1] for the first buffer, or one block early under a clamp). */
static void wrong_pick_raw(struct kept_panel *db, const struct pong_scanout_frame *frame)
{
    db[frame.target - 1].phys = 0;
}
