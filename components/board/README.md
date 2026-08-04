# board component

Purpose: Heltec WiFi LoRa 32 V3.2 HTIT-WB32LAF mapping and
board-specific safe-state controls.

Hardware compatibility ID:

    heltec-wifi-lora-32-v3.2-htit-wb32laf

The component owns:

- Board revision selection and validation.
- The private logical-signal-to-GPIO mapping.
- Fail-closed GPIO preparation.
- Active-low Vext control.
- Active-high battery-divider control.
- User LED control.
- OLED, LoRa, button, ADC and UART safe-state preparation.

Raw GPIO numbers and ESP-IDF GPIO types remain private to this
component. Public APIs return `sqd_status_t`.

GPIO0 is the user button and boot strapping input. It is never
configured or driven as an output.
