#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "driver/gpio.h"
#include "sqd_board.h"

#define SQD_BOARD_HARDWARE_COMPATIBILITY_ID "heltec-wifi-lora-32-v3.2-htit-wb32laf"

typedef enum {
    SQD_BOARD_SIGNAL_OLED_SDA = 0,
    SQD_BOARD_SIGNAL_OLED_SCL,
    SQD_BOARD_SIGNAL_OLED_RESET,
    SQD_BOARD_SIGNAL_LORA_NSS,
    SQD_BOARD_SIGNAL_LORA_SCK,
    SQD_BOARD_SIGNAL_LORA_MOSI,
    SQD_BOARD_SIGNAL_LORA_MISO,
    SQD_BOARD_SIGNAL_LORA_RESET,
    SQD_BOARD_SIGNAL_LORA_BUSY,
    SQD_BOARD_SIGNAL_LORA_DIO1,
    SQD_BOARD_SIGNAL_VEXT_CONTROL,
    SQD_BOARD_SIGNAL_USER_BUTTON,
    SQD_BOARD_SIGNAL_BATTERY_ADC,
    SQD_BOARD_SIGNAL_BATTERY_ADC_CONTROL,
    SQD_BOARD_SIGNAL_USER_LED,
    SQD_BOARD_SIGNAL_UART0_TX,
    SQD_BOARD_SIGNAL_UART0_RX,
    SQD_BOARD_SIGNAL_COUNT
} sqd_board_signal_t;

typedef struct {
    gpio_num_t gpio;
    bool active_low;
    bool defined;
} sqd_board_pin_t;

const sqd_board_pin_t *sqd_board_internal_get_pin(sqd_board_signal_t signal);

bool sqd_board_internal_mapping_is_valid(void);

sqd_board_revision_t sqd_board_internal_selected_revision(void);

const char *sqd_board_internal_compatibility_id(void);
