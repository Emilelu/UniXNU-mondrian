/* SPDX-License-Identifier: APSL-2.0 */
/* Allocation/copy excerpt: xnu ac9718fb, bsd/kern/kern_event.c:8912-8957.
 * The skipped branch preserves the first two context lines of patch 0542.
 * Included inside the test function; allocator/network plumbing is in the harness.
 */
#if 0
	}
#endif /* SKYWALK && XNU_TARGET_OS_OSX */

	/* Verify the message is small enough to fit in one mbuf w/o cluster */
	total_size = KEV_MSG_HEADER_SIZE;

	for (i = 0; i < 5; i++) {
		if (event_msg->dv[i].data_length == 0) {
			break;
		}
		total_size += event_msg->dv[i].data_length;
	}

	if (total_size > MLEN) {
		os_atomic_inc(&kevtstat.kes_toobig, relaxed);
		return EMSGSIZE;
	}

	m = m_get(wait, MT_DATA);
	if (m == 0) {
		os_atomic_inc(&kevtstat.kes_nomem, relaxed);
		return ENOMEM;
	}
	ev = mtod(m, struct kern_event_msg *);
	total_size = KEV_MSG_HEADER_SIZE;

	tmp = (char *) &ev->event_data[0];
	for (i = 0; i < 5; i++) {
		if (event_msg->dv[i].data_length == 0) {
			break;
		}

		total_size += event_msg->dv[i].data_length;
		bcopy(event_msg->dv[i].data_ptr, tmp,
		    event_msg->dv[i].data_length);
		tmp += event_msg->dv[i].data_length;
	}

	ev->id = ++static_event_id;
	ev->total_size   = total_size;
	ev->vendor_code  = event_msg->vendor_code;
	ev->kev_class    = event_msg->kev_class;
	ev->kev_subclass = event_msg->kev_subclass;
	ev->event_code   = event_msg->event_code;

	m->m_len = total_size;
