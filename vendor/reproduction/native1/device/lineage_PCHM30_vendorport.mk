# SPDX-License-Identifier: Apache-2.0
# Initial product configuration. Hardware integration is not complete.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)
$(call inherit-product, device/oppo/PCHM30_vendorport/device.mk)

PRODUCT_NAME := lineage_PCHM30_vendorport
PRODUCT_DEVICE := PCHM30_vendorport
PRODUCT_MANUFACTURER := OPPO
PRODUCT_BRAND := OPPO
PRODUCT_MODEL := OPPO A11x
