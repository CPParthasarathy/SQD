#include <inttypes.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_system.h"

#include "sdkconfig.h"

static const char *TAG = "B1.2";

void app_main(void)
{
    uint32_t heartbeat = 0;

    ESP_LOGI(TAG, "B1.2 minimal firmware started");
    ESP_LOGI(TAG, "ESP-IDF version: %s", esp_get_idf_version());
    ESP_LOGI(TAG, "Configured target: %s", CONFIG_IDF_TARGET);

    while (true) {
        ESP_LOGI(TAG, "Heartbeat: %" PRIu32, heartbeat++);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
