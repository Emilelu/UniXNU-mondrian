/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * K60 audio service ABI: one control page and one playback ring shared with
 * the userland HAL. The ring uses the K60 PCM geometry from PongAudioRing.h
 * (S24_LE in a 32-bit word, 8 bytes per frame). The service consumes whole
 * periods at 1024 frames and forwards them to pong_audio_submit().
 */
#ifndef PONG_AUDIO_SERVICE_ABI_H
#define PONG_AUDIO_SERVICE_ABI_H

#include <stdint.h>

#define PONG_AUDIO_SERVICE_CLASS              "PongAudio"
#define PONG_AUDIO_SERVICE_MAGIC              0x53484155u /* 'SHAU' */
#define PONG_AUDIO_SERVICE_VERSION            3u
#define PONG_AUDIO_SERVICE_RATE               48000u
#define PONG_AUDIO_SERVICE_CHANNELS           2u
#define PONG_AUDIO_SERVICE_FRAME_BYTES        8u /* two S24_LE words */
#define PONG_AUDIO_SERVICE_PERIOD_FRAMES      1024u
#define PONG_AUDIO_SERVICE_RING_FRAMES        65536u
#define PONG_AUDIO_SERVICE_LEAD_FRAMES        14400u
#define PONG_AUDIO_SERVICE_RING_BYTES         \
	(PONG_AUDIO_SERVICE_RING_FRAMES * PONG_AUDIO_SERVICE_FRAME_BYTES)

enum {
	PongAudioServiceMemoryControl = 0,
	PongAudioServiceMemoryOutput = 1,
};

enum {
	PongAudioServiceStartOutput = 0,
	PongAudioServiceStopOutput = 1,
	PongAudioServiceSetHostClock = 4,
};

enum {
	PongAudioServiceOutputRunning = 1u << 0,
	PongAudioServiceOutputReady = 1u << 1,
};

/* out_write and out_read are monotonic frame counters modulo the ring. The
 * HAL writes at out_write % ring_frames and advances out_write; the service
 * reads at out_read % ring_frames and advances out_read after each period.
 * Both counters are 64-bit so a long-running HAL cannot wrap a 32-bit count.
 *
 * ticks_per_frame_q32 / out_anchor_host / out_frames make the machine clock
 * explicit to CoreAudio: sample time zero is the frame played at
 * out_anchor_host and one frame lasts ticks_per_frame_q32 / 2^32 host ticks.
 * out_seq is incremented around anchor updates (odd while writing). This is
 * the 19.2 MHz handshake from porting/power; CoreAudio otherwise assumes a
 * 24 MHz host clock and runs its IO cycle 25 percent long.
 */
typedef struct {
	uint32_t magic;
	uint32_t version;
	uint32_t rate;
	uint32_t channels;
	uint32_t frame_bytes;
	uint32_t period_frames;
	uint32_t ring_frames;
	uint32_t lead_frames;
	volatile uint32_t state;
	volatile uint32_t out_late;
	volatile uint64_t out_write;
	volatile uint64_t out_read;
	volatile uint32_t out_seq;
	uint32_t reserved0;
	volatile uint64_t ticks_per_frame_q32;
	volatile uint64_t out_anchor_host;
	volatile uint64_t out_frames;
} PongAudioServiceControl;

#endif /* PONG_AUDIO_SERVICE_ABI_H */
