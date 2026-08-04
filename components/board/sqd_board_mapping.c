#include "sqd_board_internal.h"

static const sqd_board_pin_t s_board_pins[SQD_BOARD_SIGNAL_COUNT] = {
    [SQD_BOARD_SIGNAL_OLED_SDA] = {
        .gpio = GPIO_NUM_17,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_OLED_SCL] = {
        .gpio = GPIO_NUM_18,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_OLED_RESET] = {
        .gpio = GPIO_NUM_21,
        .active_low = true,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_NSS] = {
        .gpio = GPIO_NUM_8,
        .active_low = true,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_SCK] = {
        .gpio = GPIO_NUM_9,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_MOSI] = {
        .gpio = GPIO_NUM_10,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_MISO] = {
        .gpio = GPIO_NUM_11,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_RESET] = {
        .gpio = GPIO_NUM_12,
        .active_low = true,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_BUSY] = {
        .gpio = GPIO_NUM_13,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_LORA_DIO1] = {
        .gpio = GPIO_NUM_14,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_VEXT_CONTROL] = {
        .gpio = GPIO_NUM_36,
        .active_low = true,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_USER_BUTTON] = {
        .gpio = GPIO_NUM_0,
        .active_low = true,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_BATTERY_ADC] = {
        .gpio = GPIO_NUM_1,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_BATTERY_ADC_CONTROL] = {
        .gpio = GPIO_NUM_37,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_USER_LED] = {
        .gpio = GPIO_NUM_35,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_UART0_TX] = {
        .gpio = GPIO_NUM_43,
        .active_low = false,
        .defined = true,
    },
    [SQD_BOARD_SIGNAL_UART0_RX] = {
        .gpio = GPIO_NUM_44,
        .active_low = false,
        .defined = true,
    },
};

_Static_assert(
    (sizeof(s_board_pins) / sizeof(s_board_pins[0])) ==
        SQD_BOARD_SIGNAL_COUNT,
    "Board mapping must define every logical signal."
);

const sqd_board_pin_t *sqd_board_internal_get_pin(
    sqd_board_signal_t signal
)
{
    if ((signal < 0) || (signal >= SQD_BOARD_SIGNAL_COUNT)) {
        return NULL;
    }

    return &s_board_pins[signal];
}

bool sqd_board_internal_mapping_is_valid(void)
{
    size_t first_index;
    size_t second_index;

    for (first_index = 0;
         first_index < SQD_BOARD_SIGNAL_COUNT;
         ++first_index) {
        const sqd_board_pin_t *first = &s_board_pins[first_index];

        if (!first->defined) {
            return false;
        }

        if ((first->gpio < GPIO_NUM_0) ||
            (first->gpio >= GPIO_NUM_MAX)) {
            return false;
        }

        for (second_index = first_index + 1;
             second_index < SQD_BOARD_SIGNAL_COUNT;
             ++second_index) {
            const sqd_board_pin_t *second =
                &s_board_pins[second_index];

            if (first->gpio == second->gpio) {
                return false;
            }
        }
    }

    return true;
}

sqd_board_revision_t sqd_board_internal_selected_revision(void)
{
#if CONFIG_SQD_BOARD_HELTEC_WIFI_LORA_32_V3_2
    return SQD_BOARD_REVISION_HELTEC_WIFI_LORA_32_V3_2;
#else
    return SQD_BOARD_REVISION_UNKNOWN;
#endif
}

const char *sqd_board_internal_compatibility_id(void)
{
    return SQD_BOARD_HARDWARE_COMPATIBILITY_ID;
}
