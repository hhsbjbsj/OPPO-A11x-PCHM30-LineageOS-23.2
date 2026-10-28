# SPDX-License-Identifier: Apache-2.0
# This stage validates product selection and the build dependency graph.
# Factory vendor/odm blobs, SELinux mappings and boot ramdisk are not integrated.
PRODUCT_SHIPPING_API_LEVEL := 28
PRODUCT_USE_DYNAMIC_PARTITIONS := false
AB_OTA_UPDATER := false

# The verified factory vendor declares VNDK 30.
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
PRODUCT_BUILD_VBMETA_IMAGE := false

# Initial UI dimensions; device display overlays remain to be integrated.
TARGET_SCREEN_WIDTH := 720
TARGET_SCREEN_HEIGHT := 1600

PRODUCT_SOONG_NAMESPACES += device/oppo/PCHM30_vendorport

PRODUCT_DEX_PREOPT_DEFAULT_COMPILER_FILTER := verify
