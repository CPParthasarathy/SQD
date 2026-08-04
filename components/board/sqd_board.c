#include "sqd_board.h"

#include <stdint.h>

#include "driver/gpio.h"
#include "esp_err.h"
#include "sqd_board_internal.h"

static sqd_board_revision_t s_board_revision =
    SQD_BOARD_REVISION_UNKNOWN;

static bool s_board_initialized;

static sqd_status_t sqd_board_translate_gpio_error(
    esp_err_t error
)
{
    switch (error) {
        case ESP_OK:
            return SQD_STATUS_OK;

        case ESP_ERR_INVALID_ARG:
            return SQD_STATUS_INVALID_ARGUMENT;

        case ESP_ERR_INVALID_STATE:
            return SQD_STATUS_INVALID_STATE;

        case ESP_ERR_NO_MEM:
            return SQD_STATUS_NO_MEMORY;

        default:
            return SQD_STATUS_IO;
    }
}

static void sqd_board_record_first_error(
    sqd_status_t candidate,
    sqd_status_t *first_error
)
{
    if ((first_error != NULL) &&
        (*first_error == SQD_STATUS_OK) &&
        (candidate != SQD_STATUS_OK)) {
        *first_error = candidate;
    }
}

static sqd_status_t sqd_board_configure_input(
    sqd_board_signal_t signal,
    gpio_pullup_t pull_up,
    gpio_pulldown_t pull_down
)
{
    const sqd_board_pin_t *pin =
        sqd_board_internal_get_pin(signal);

    if ((pin == NULL) || !pin->defined) {
        return SQD_STATUS_INTEGRITY;
    }

    const gpio_config_t configuration = {
        .pin_bit_mask = UINT64_C(1) << pin->gpio,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = pull_up,
        .pull_down_en = pull_down,
        .intr_type = GPIO_INTR_DISABLE,
    };

    return sqd_board_translate_gpio_error(
        gpio_config(&configuration)
    );
}

static sqd_status_t sqd_board_configure_output(
    sqd_board_signal_t signal,
    bool asserted,
    bool open_drain
)
{
    const sqd_board_pin_t *pin =
        sqd_board_internal_get_pin(signal);

    if ((pin == NULL) || !pin->defined) {
        return SQD_STATUS_INTEGRITY;
    }

    const uint32_t level =
        (uint32_t)(pin->active_low ? !asserted : asserted);

    sqd_status_t status = sqd_board_translate_gpio_error(
        gpio_set_level(pin->gpio, level)
    );

    if (status != SQD_STATUS_OK) {
        return status;
    }

    const gpio_config_t configuration = {
        .pin_bit_mask = UINT64_C(1) << pin->gpio,
        .mode = open_drain ?
            GPIO_MODE_OUTPUT_OD : GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    status = sqd_board_translate_gpio_error(
        gpio_config(&configuration)
    );

    if (status != SQD_STATUS_OK) {
        return status;
    }

    return sqd_board_translate_gpio_error(
        gpio_set_level(pin->gpio, level)
    );
}

static sqd_status_t sqd_board_write_output(
    sqd_board_signal_t signal,
    bool asserted
)
{
    const sqd_board_pin_t *pin =
        sqd_board_internal_get_pin(signal);

    if ((pin == NULL) || !pin->defined) {
        return SQD_STATUS_INTEGRITY;
    }

    const uint32_t level =
        (uint32_t)(pin->active_low ? !asserted : asserted);

    return sqd_board_translate_gpio_error(
        gpio_set_level(pin->gpio, level)
    );
}

static sqd_status_t sqd_board_apply_safe_state(void)
{
    sqd_status_t first_error = SQD_STATUS_OK;

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_VEXT_CONTROL,
            false,
            false
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_BATTERY_ADC_CONTROL,
            false,
            false
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_USER_LED,
            false,
            false
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_LORA_NSS,
            false,
            false
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_LORA_RESET,
            false,
            false
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_OLED_RESET,
            true,
            false
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_OLED_SDA,
            true,
            true
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_output(
            SQD_BOARD_SIGNAL_OLED_SCL,
            true,
            true
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_USER_BUTTON,
            GPIO_PULLUP_ENABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_BATTERY_ADC,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_LORA_SCK,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_LORA_MOSI,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_LORA_MISO,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_LORA_BUSY,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_LORA_DIO1,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    sqd_board_record_first_error(
        sqd_board_configure_input(
            SQD_BOARD_SIGNAL_UART0_RX,
            GPIO_PULLUP_DISABLE,
            GPIO_PULLDOWN_DISABLE
        ),
        &first_error
    );

    return first_error;
}

static sqd_status_t sqd_board_validate_runtime_state(void)
{
    if (!s_board_initialized) {
        return SQD_STATUS_INVALID_STATE;
    }

    if (s_board_revision ==
        SQD_BOARD_REVISION_HELTEC_WIFI_LORA_32_V3_2) {
        return SQD_STATUS_OK;
    }

    if (s_board_revision == SQD_BOARD_REVISION_UNKNOWN) {
        return SQD_STATUS_NOT_SUPPORTED;
    }

    return SQD_STATUS_INTEGRITY;
}

static sqd_status_t sqd_board_fail_closed(
    sqd_status_t failure
)
{
    (void)sqd_board_apply_safe_state();
    s_board_initialized = false;
    s_board_revision = SQD_BOARD_REVISION_UNKNOWN;

    return failure;
}

sqd_status_t sqd_board_prepare_safe_state(void)
{
    const sqd_status_t status =
        sqd_board_apply_safe_state();

    s_board_initialized = false;
    s_board_revision = SQD_BOARD_REVISION_UNKNOWN;

    return status;
}

sqd_status_t sqd_board_initialize(void)
{
    if (s_board_initialized) {
        return SQD_STATUS_ALREADY_INITIALIZED;
    }

    s_board_initialized = false;
    s_board_revision = SQD_BOARD_REVISION_UNKNOWN;

    if (!sqd_board_internal_mapping_is_valid()) {
        return sqd_board_fail_closed(SQD_STATUS_INTEGRITY);
    }

    const sqd_status_t safe_state_status =
        sqd_board_apply_safe_state();

    if (safe_state_status != SQD_STATUS_OK) {
        return sqd_board_fail_closed(safe_state_status);
    }

    const sqd_board_revision_t selected_revision =
        sqd_board_internal_selected_revision();

    if (selected_revision == SQD_BOARD_REVISION_UNKNOWN) {
        return sqd_board_fail_closed(
            SQD_STATUS_NOT_SUPPORTED
        );
    }

    if (selected_revision !=
        SQD_BOARD_REVISION_HELTEC_WIFI_LORA_32_V3_2) {
        return sqd_board_fail_closed(SQD_STATUS_INTEGRITY);
    }

    s_board_revision = selected_revision;
    s_board_initialized = true;

    return SQD_STATUS_OK;
}

sqd_status_t sqd_board_get_revision(
    sqd_board_revision_t *revision
)
{
    if (revision == NULL) {
        return SQD_STATUS_INVALID_ARGUMENT;
    }

    const sqd_status_t state_status =
        sqd_board_validate_runtime_state();

    if (state_status != SQD_STATUS_OK) {
        return state_status;
    }

    *revision = s_board_revision;
    return SQD_STATUS_OK;
}

sqd_status_t sqd_board_set_vext_enabled(bool enabled)
{
    const sqd_status_t state_status =
        sqd_board_validate_runtime_state();

    if (state_status != SQD_STATUS_OK) {
        return state_status;
    }

    const sqd_status_t write_status =
        sqd_board_write_output(
            SQD_BOARD_SIGNAL_VEXT_CONTROL,
            enabled
        );

    if (write_status != SQD_STATUS_OK) {
        return sqd_board_fail_closed(write_status);
    }

    return SQD_STATUS_OK;
}

sqd_status_t sqd_board_set_battery_measurement_enabled(
    bool enabled
)
{
    const sqd_status_t state_status =
        sqd_board_validate_runtime_state();

    if (state_status != SQD_STATUS_OK) {
        return state_status;
    }

    const sqd_status_t write_status =
        sqd_board_write_output(
            SQD_BOARD_SIGNAL_BATTERY_ADC_CONTROL,
            enabled
        );

    if (write_status != SQD_STATUS_OK) {
        return sqd_board_fail_closed(write_status);
    }

    return SQD_STATUS_OK;
}

sqd_status_t sqd_board_set_user_led(bool enabled)
{
    const sqd_status_t state_status =
        sqd_board_validate_runtime_state();

    if (state_status != SQD_STATUS_OK) {
        return state_status;
    }

    const sqd_status_t write_status =
        sqd_board_write_output(
            SQD_BOARD_SIGNAL_USER_LED,
            enabled
        );

    if (write_status != SQD_STATUS_OK) {
        return sqd_board_fail_closed(write_status);
    }

    return SQD_STATUS_OK;
}
