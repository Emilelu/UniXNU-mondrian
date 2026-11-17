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
#define PONG_AUDIO_SERVICE_VERSION            2u
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
} PongAudioServiceControl;

#endif /* PONG_AUDIO_SERVICE_ABI_H */
