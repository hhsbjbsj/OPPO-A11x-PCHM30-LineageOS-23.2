# SPDX-License-Identifier: Apache-2.0
# PCHM30 source build product with legacy-kernel compatibility patches.
# The companion tested-firmware archive provides the verified vendor/odm/boot.
PRODUCT_SHIPPING_API_LEVEL := 28
PRODUCT_USE_DYNAMIC_PARTITIONS := false
AB_OTA_UPDATER := false

# The verified factory vendor declares VNDK 30.
PRODUCT_EXTRA_VNDK_VERSIONS += 30
# The verified factory kernel has CONFIG_USERFAULTFD disabled.
PRODUCT_ENABLE_UFFD_GC := false

# Keep product/system_ext under the existing physical system partition.
PRODUCT_BUILD_PRODUCT_IMAGE := false
PRODUCT_BUILD_SYSTEM_EXT_IMAGE := false
PRODUCT_BUILD_BOOT_IMAGE := false
PRODUCT_BUILD_INIT_BOOT_IMAGE := false
PRODUCT_BUILD_VENDOR_BOOT_IMAGE := false
PRODUCT_BUILD_RECOVERY_IMAGE := false
PRODUCT_BUILD_RAMDISK_IMAGE := false
PRODUCT_BUILD_VENDOR_IMAGE := false
PRODUCT_BUILD_ODM_IMAGE := false
PRODUCT_BUILD_USERDATA_IMAGE := false
PRODUCT_BUILD_CACHE_IMAGE := false
PRODUCT_BUILD_VBMETA_IMAGE := true

# Display dimensions retained from the tested bring-up product.
TARGET_SCREEN_WIDTH := 720
TARGET_SCREEN_HEIGHT := 1600

PRODUCT_SOONG_NAMESPACES += device/oppo/PCHM30

# Explicitly require the restored factory-vendor compatibility APEX.
PRODUCT_PACKAGES += com.android.vndk.v30



# BEGIN PCHM30 NATIVE FULL TEST1
PRODUCT_ENFORCE_VINTF_MANIFEST := true

# PCHM30 legacy-kernel bring-up profile. This does not enable working BPF.
PRODUCT_PRODUCT_PROPERTIES += ro.bpf.kver_override=5.10.239
