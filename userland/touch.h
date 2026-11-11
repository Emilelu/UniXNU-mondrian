#ifndef PONG_TOUCH_H
#define PONG_TOUCH_H
#include <stdint.h>
#define PONG_TOUCH_DOWN 1
#define PONG_TOUCH_MOVE 2
#define PONG_TOUCH_UP 3
#define PONG_BUTTON_DOWN 4
#define PONG_BUTTON_UP 5
#define PONG_BUTTON_POWER 0
#define PONG_BUTTON_VOLUME_UP 1
#define PONG_BUTTON_VOLUME_DOWN 2
/* The kernel scales K60 raw 14400x32000 axes into this fixed wire interval. */
#define PONG_TOUCH_COORD_MAX 65535u
struct pong_touch {uint64_t time;uint32_t type,finger,x,y;};
void pong_touch_start(void);
#endif
