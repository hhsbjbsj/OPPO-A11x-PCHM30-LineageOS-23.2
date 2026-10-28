# SPDX-License-Identifier: Apache-2.0
# PCHM30 source-built System with separately verified firmware inputs.
DEVICE_PATH := device/oppo/PCHM30

TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_VARIANT := generic
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-a
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi

TARGET_BOARD_PLATFORM := trinket
TARGET_BOOTLOADER_BOARD_NAME := trinket
TARGET_USES_64_BIT_BINDER := true

# Kernel/boot/vendor are verified firmware inputs; Recovery is preserved.
TARGET_NO_KERNEL := true
TARGET_NO_RECOVERY := true
TARGET_NO_BOOTLOADER := true
TARGET_NO_RADIOIMAGE := true

# Sizes were checked against the phone and its factory partition images.
BOARD_FLASH_BLOCK_SIZE := 262144
BOARD_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 67108864
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 5473566720
BOARD_VENDORIMAGE_PARTITION_SIZE := 1681915904
BOARD_CACHEIMAGE_PARTITION_SIZE := 268435456
BOARD_DTBOIMG_PARTITION_SIZE := 25165824

TARGET_USERIMAGES_USE_EXT4 := true
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4
TARGET_COPY_OUT_VENDOR := vendor
TARGET_COPY_OUT_PRODUCT := system/product
TARGET_COPY_OUT_SYSTEM_EXT := system/system_ext

BOARD_VNDK_VERSION := current



# BEGIN PCHM30 NATIVE FULL TEST1
BOARD_PREBUILT_BOOTIMAGE := vendor/oppo/pchm30-tested-firmware/boot.img
BOARD_PREBUILT_VENDORIMAGE := vendor/oppo/pchm30-tested-firmware/vendor.img
BOARD_PREBUILT_DTBOIMAGE := vendor/oppo/pchm30-tested-firmware/dtbo.img
TARGET_OTA_ALLOW_NON_AB := true
BOARD_BOOT_HEADER_VERSION := 1
BOARD_KERNEL_PAGESIZE := 4096
TARGET_COPY_OUT_ODM := odm
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_AVB_ENABLE := true
BOARD_AVB_ALGORITHM := SHA256_RSA4096
BOARD_AVB_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_ROLLBACK_INDEX := 0
# Unlocked-device bring-up; factory vbmeta would describe the old system.
BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 3
DEVICE_MANIFEST_FILE := $(DEVICE_PATH)/factory-vintf/vendor/manifest.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.atrace@1.0-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.cas@1.2-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.gnss@2.1-service-qti.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.graphics.composer-qti-display.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.graphics.mapper-impl-qti-display.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.health@2.1.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.lights-qti.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.neuralnetworks@1.3-service-qti.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.sensors@2.0-multihal.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.thermal@2.0-service.qti.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.usb@1.0-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.wifi.hostapd.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/android.hardware.wifi@1.0-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/manifest.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/manifest_android.hardware.drm@1.3-service.clearkey.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/oplus_wifi_supplicant_device.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/power.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/vendor.qti.gnss@4.0-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/vendor.qti.hardware.display.allocator-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/vendor.qti.hardware.servicetracker@1.2-service.xml $(DEVICE_PATH)/factory-vintf/vendor/manifest/vendor.qti.hardware.vibrator.service.xml
DEVICE_MATRIX_FILE := $(DEVICE_PATH)/factory-vintf/vendor/compatibility_matrix.xml
ODM_MANIFEST_FILES := $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_android.hardware.drm@1.3-service.widevine.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_dax_dolby.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_engineer.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_engsensor.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplusSensor.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_bluetooth_audio.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_charger.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_engcamera.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_fido.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_mmdisplayfeature.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_orms.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_stability_project.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_thermalmntcfg.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_oplus_touch.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/manifest_transmessage.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/oplus_wifi_service_device.xml $(DEVICE_PATH)/factory-vintf/odm/manifest/telephony_manifest.xml
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += $(DEVICE_PATH)/factory-vintf/framework-oem-extensions.xml
