# SPDX-License-Identifier: Apache-2.0
# PCHM30 source product; see README for firmware and validation scope.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)
$(call inherit-product, device/oppo/PCHM30/device.mk)

PRODUCT_NAME := lineage_PCHM30
PRODUCT_DEVICE := PCHM30
PRODUCT_MANUFACTURER := OPPO
PRODUCT_BRAND := OPPO
PRODUCT_MODEL := OPPO A11x
