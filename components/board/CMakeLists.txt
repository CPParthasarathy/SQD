if(NOT CMAKE_SCRIPT_MODE_FILE)
    set(SQD_BOARD_SELECTION_COUNT 0)

    if(CONFIG_SQD_BOARD_HELTEC_WIFI_LORA_32_V3_2)
        math(EXPR SQD_BOARD_SELECTION_COUNT
            "${SQD_BOARD_SELECTION_COUNT} + 1"
        )
    endif()

    if(NOT SQD_BOARD_SELECTION_COUNT EQUAL 1)
        message(FATAL_ERROR
            "Exactly one SQD board must be selected. "
            "Enable CONFIG_SQD_BOARD_HELTEC_WIFI_LORA_32_V3_2."
        )
    endif()
endif()

idf_component_register(
    SRCS
        "sqd_board.c"
        "sqd_board_mapping.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "private"
    REQUIRES core
    PRIV_REQUIRES esp_driver_gpio
)
