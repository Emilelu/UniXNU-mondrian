/* Minimal libxpc declarations for SDKs that ship libxpc but not its headers. */
#pragma once
#include <stdint.h>
#include <dispatch/dispatch.h>
typedef const struct _xpc_type_s *xpc_type_t;
typedef void *xpc_object_t;
typedef xpc_object_t xpc_connection_t;
typedef void (^xpc_handler_t)(xpc_object_t);
typedef uint64_t xpc_connection_mach_service_flags_t;
extern const struct _xpc_type_s xpc_type_dictionary;
extern const struct _xpc_type_s xpc_type_connection;
#define XPC_TYPE_DICTIONARY (&xpc_type_dictionary)
#define XPC_TYPE_CONNECTION (&xpc_type_connection)
#define XPC_CONNECTION_MACH_SERVICE_LISTENER ((xpc_connection_mach_service_flags_t)1)
xpc_type_t xpc_get_type(xpc_object_t);
xpc_object_t xpc_dictionary_create_reply(xpc_object_t);
const char *xpc_dictionary_get_string(xpc_object_t, const char *);
xpc_object_t xpc_dictionary_get_value(xpc_object_t, const char *);
void xpc_dictionary_set_int64(xpc_object_t, const char *, int64_t);
void xpc_dictionary_set_string(xpc_object_t, const char *, const char *);
xpc_connection_t xpc_dictionary_get_remote_connection(xpc_object_t);
void xpc_connection_send_message(xpc_connection_t, xpc_object_t);
void xpc_release(xpc_object_t);
void xpc_connection_set_target_queue(xpc_connection_t, dispatch_queue_t);
void xpc_connection_set_event_handler(xpc_connection_t, xpc_handler_t);
void xpc_connection_resume(xpc_connection_t);
