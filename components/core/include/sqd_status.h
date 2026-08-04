#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SQD_STATUS_OK = 0,
    SQD_STATUS_INVALID_ARGUMENT = 1,
    SQD_STATUS_INVALID_STATE = 2,
    SQD_STATUS_ALREADY_INITIALIZED = 3,
    SQD_STATUS_NOT_FOUND = 4,
    SQD_STATUS_BUSY = 5,
    SQD_STATUS_TIMEOUT = 6,
    SQD_STATUS_IO = 7,
    SQD_STATUS_INTEGRITY = 8,
    SQD_STATUS_AUTHORIZATION = 9,
    SQD_STATUS_NO_MEMORY = 10,
    SQD_STATUS_NOT_SUPPORTED = 11,
    SQD_STATUS_CANCELLED = 12,
    SQD_STATUS_INTERNAL = 13
} sqd_status_t;

#ifdef __cplusplus
}
#endif
