# PCHM30 PBRP Recovery Data 解密失败深度剖析与 BusyBox 永久集成方案（交给 GPT 专项重编指引）

- **机型:** OPPO A11x / A9 2020 (`PCHM30` / `sm6125` / `trinket`)
- **当前 Recovery:** PBRP (PitchBlack Recovery Project v3.2 / TWRP 基底, Android 12 SDK 32 编译)
- **目标系统:** LineageOS 23.2 (Android 16 QPR2 / 25Q4 / Linux 4.14.357-perf+)
- **输出日志依据:** `C:\Users\user\Desktop\ls\recovery_decrypt_investigation.log`

---

## 任务目标
解决当前 Recovery 的两大核心痛点，重新编译产出适用于 Android 16 的无感解密与全自动刷机 Recovery：
1. **彻底解决 `/data` 无法解密问题（从根本上阐明为何 GSI 能解密而 Android 16 失败，并给出适配方案）。**
2. **彻底解决每次刷机报 `ERROR: PBRP busybox required; no partitions were written.` 的问题（在 Recovery 源码树与刷机包双重集成 BusyBox）。**

---

## 一、 为什么此前 GSI (Android 11~13) 可以解密，而 Android 16 失败？

在真机恢复模式下抓取到的底层日志给出了确凿的硬件级故障链：

```text
[recovery.log 关键行]
I:File Based Encryption is present
Attempting to initialize DE keys
DEBUG:prepdecrypt::SDK version: 32
DEBUG:prepdecrypt::SETPATCH Override flag found.
I:prepdecrypt::SETPATCH=false
DEBUG:prepdecrypt::OS version exists! ro.build.version.release=16.0.0
DEBUG:prepdecrypt::Security Patch Level exists! ro.build.version.security_patch=2026-07-01
I:prepdecrypt::Script complete. Device ready for decryption.
...
10-27 14:25:00.680 KeymasterUtils: TA Major Version: 4, TA Minor Version: 529
10-27 14:25:01.266 recovery: reading blob_file: /data/unencrypted/key/keymaster_key_blob
10-27 14:25:01.276 KeyMasterHalDevice: Begin send cmd failed, ret: 0, resp->status: -62
10-27 14:25:01.287 KeyMasterHalDevice: Upgrade key send cmd failed, ret: 0, resp->status: -38
...
fscrypt_initialize_systemwide_keys returned fail
```

### 1. 核心致命点 1：TrustZone Keymaster TA 版本绑定拒绝（-62: `KM_ERROR_KEY_REQUIRES_UPGRADE`）
- **机制原理：** 高通 QSEE / TrustZone 中的 Keymaster 4.0 TA 会在生成或使用密钥时，严格校验当前的 `OS_VERSION`、`OS_PATCHLEVEL`（安全补丁日期）以及 `VENDOR_PATCHLEVEL`。
- **此前 GSI 能解密的原因：** GSI 多为 Android 11/12/13，其安全补丁日期与 Vendor 厂商底包日期（2022-05-05）接近，PBRP 也是基于 Android 12 编译的，版本未跨越大代际，TrustZone TA 认为环境可信，顺利派生密钥。
- **Android 16 失败原因：**
  - Android 16 (LineageOS 23.2) 的安全补丁被写入了 `2026-07-01`，系统版本为 `16.0.0`。在系统首次开机完成 FBE 加密时，TA 将 Key Blob 与 Android 16 的版本信息进行了防回滚绑定。
  - 当重启进入 Android 12 源码架构的 PBRP 时，`prepdecrypt.sh` 的 `SETPATCH` 为 `false`，传入 TA 的校验参数与 Android 16 产生严重冲突，Keymaster TA 硬件直接打回，返回 **`resp->status: -62`（`KM_ERROR_KEY_REQUIRES_UPGRADE`）**。
  - 随后 Recovery 尝试调用 `UpgradeKey` 想要更新 Key Blob，但因为没有 Android 16 主系统的加密上下文，TA 再次报错 **`resp->status: -38`（`KM_ERROR_INVALID_KEY_BLOB`）**，导致 DE 密钥加载彻底中断！

### 2. 核心致命点 2：fscrypt v1 与 fscrypt v2 政策与 Keystore 2.0 跨代断层
- 查看 `/data/unencrypted/mode`：当前设备为 `ice:aes-256-cts:v1+wrappedkey_v0`。
- 当前 PBRP 是基于 **Android 12 (SDK 32)** 的 recovery 架构，而 Android 16 引入了全新的 **fscrypt v2**、新的策略描述符以及更新的 `keystore2` AIDL 通信协议。Android 12 的 `libfscrypt` / `vold` 无法正确解析由 Android 16 派生的用户级加密策略（User DE/CE keys）。

### 3. 核心致命点 3：`recovery.fstab` 配置歧义
- Recovery 的 `/etc/recovery.fstab` 中配置：
  `keydirectory=/metadata/vold/metadata_encryption` 并且标为 `f2fs`。
- 但实际上该设备的 `/data` 实际是 **ext4** 文件系统，真实的密钥存放在传统的 `/data/unencrypted/key` 中，同时 `/metadata` 分区在 Recovery 阶段默认未被自动挂载。

---

## 二、 为什么每次刷机都报缺少 BusyBox？

- **根本原因：**
  ROM 刷机包中的 `META-INF/com/google/android/update-binary` 是一个 Shell 脚本，其内置了硬编码检测逻辑：
  ```bash
  for candidate in /sbin/busybox /system/bin/busybox /system/xbin/busybox; do
      if [ -x "$candidate" ]; then BB="$candidate"; break; fi
  done
  if [ -z "$BB" ]; then
      echo "ERROR: PBRP busybox required; no partitions were written."
      exit 1
  fi
  ```
  但当前的 PBRP Recovery 镜像的 root ramdisk `/sbin/` 下只有 `bash`、`nano`、`magiskboot` 等，**完全没有编译或放置 `busybox`**！因此每次卡刷都会触发该错误退出，必须手动通过 `adb push` 补救。

---

## 三、 GPT 重编与集成执行指引（请 GPT 按照以下方案执行）

### 任务 1：在 Recovery 源码树中永久集成 BusyBox

在 Recovery 设备树（`device/oppo/PCHM30` 或 `device/oppo/trinket-common`）中进行如下修改：

1. **方式 A（源码模块集成，推荐）：**
   在 `BoardConfig.mk` 中确保包含：
   ```make
   # 集成 BusyBox 模块至 Recovery
   TARGET_RECOVERY_DEVICE_MODULES += busybox
   TW_USE_TOOLBOX := false
   ```
2. **方式 B（静态二进制预置，最稳妥）：**
   在 Recovery 设备树的根目录覆盖层 `recovery/root/sbin/` 下放入静态编译的 ARM64 `busybox`：
   - 路径：`device/oppo/PCHM30/recovery/root/sbin/busybox`
   - 权限：设置 `chmod 755`
   并在 `Android.mk` / `device.mk` 中添加拷贝规则：
   ```make
   PRODUCT_COPY_FILES += \
       $(DEVICE_PATH)/recovery/root/sbin/busybox:recovery/root/sbin/busybox
   ```

3. **双重保险（ROM 端 update-binary 解耦）：**
   在定制 ROM 的 `update-binary` 中，放宽对 busybox 的死板依赖：
   ```bash
   # 如果找不到 busybox，自动回退到 toybox 或 toolbox，避免强退
   if [ -z "$BB" ]; then
       if command -v toybox >/dev/null 2>&1; then
           BB="toybox"
       elif [ -x "/system/bin/toybox" ]; then
           BB="/system/bin/toybox"
       else
           echo "Warning: busybox not found, falling back to standard shell builtins."
       fi
   fi
   ```

---

### 任务 2：修复 Recovery 针对 Android 16 的 Data 解密

1. **同步 `prepdecrypt` 的系统版本与补丁（Patchlevel Spoofing）：**
   在 Recovery 的 `init.recovery.qcom_decrypt.rc` 或 `prepdecrypt.sh` 中：
   强制将 `ro.build.version.release` 与 `ro.build.version.security_patch` 设置为与 Android 16 完全一致的数值：
   ```bash
   resetprop ro.build.version.release "16.0.0"
   resetprop ro.build.version.sdk "36"
   resetprop ro.build.version.security_patch "2026-07-01"
   resetprop prepdecrypt.setpatch "true"
   ```
   **关键：** 必须确保 `SETPATCH=true`，这样 `prepdecrypt.sh` 会自动去挂载并读取 `/system/build.prop` 中的真实补丁日期覆盖当前属性，否则 Keymaster TA 会始终报 `-62` 错误拒绝对接。

2. **修正 `recovery.fstab` 中的 Data 与 Metadata 描述：**
   将 `userdata` 的文件系统修正为 `ext4`（或使用 `auto`），并明确指定 Key 目录：
   ```text
   /dev/block/bootdevice/by-name/metadata    /metadata    ext4    noatime,nosuid,nodev,discard    wait,formattable
   /dev/block/bootdevice/by-name/userdata    /data        ext4    noatime,nosuid,nodev,barrier=1,inlinecrypt    latemount,wait,check,fileencryption=ice:wrappedkey,keydirectory=/data/unencrypted/key
   ```

3. **更新 Recovery 源码基底至 Android 14/15/16 TWRP 树（长效根治方案）：**
   - 当前 Recovery 的 SDK 仍为 32（Android 12），建议使用基于 **TWRP 14 (AOSP 14 / SDK 34) 或更高** 的分支进行重编。
   - 高版本 TWRP 自带对 `fscrypt v2`、`Keystore 2.0` 以及高通 WrappedKey 的完整原生支持，能天然兼容 Android 16 QPR2 的文件系统加密机制。
