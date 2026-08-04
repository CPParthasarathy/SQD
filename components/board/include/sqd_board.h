#pragma once

#include <stdbool.h>

#include "sqd_status.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SQD_BOARD_REVISION_UNKNOWN = 0,
    SQD_BOARD_REVISION_HELTEC_WIFI_LORA_32_V3_2 = 1
} sqd_board_revision_t;

/**
 * Prepare every board-owned GPIO in the accepted fail-closed state.
 *
 * This operation is safe before normal board initialization.
 */
sqd_status_t sqd_board_prepare_safe_state(void);

/**
 * Validate the selected board revision and initialize board ownership.
 *
 * Peripheral power remains disabled after successful initialization.
 */
sqd_status_t sqd_board_initialize(void);

/**
 * Return the validated runtime board revision.
 */
sqd_status_t sqd_board_get_revision(
    sqd_board_revision_t *revision
);

/**
 * Enable or disable the active-low Vext peripheral power rail.
 */
sqd_status_t sqd_board_set_vext_enabled(bool enabled);

/**
 * Enable or disable the active-high battery divider.
 */
sqd_status_t sqd_board_set_battery_measurement_enabled(
    bool enabled
);

/**
 * Illuminate or extinguish the active-high user LED.
 */
sqd_status_t sqd_board_set_user_led(bool enabled);

#ifdef __cplusplus
}
#endif
