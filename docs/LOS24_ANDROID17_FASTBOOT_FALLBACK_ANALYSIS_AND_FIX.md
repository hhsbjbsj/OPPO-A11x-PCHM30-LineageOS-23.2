# OPPO A11x (PCHM30) LineageOS 24 (Android 17 / SDK 37) 刷入后重启回 Fastboot 根因深度剖析与 GPT 修复方案

## 1. 现场诊断背景与提取文件概况

- **设备型号**: OPPO A11x / A9 2020 (`PCHM30`，高通骁龙 665 / Trinket `sm6125`)
- **刷入系统包**: `PCHM30-LOS24.0-ANDROID17-EXPERIMENTAL-20261029T054332Z.zip`
- **刷入现象**: 刷入成功后，手机尝试启动，卡在第一屏/第二屏数秒后，直接自动重启掉入 **Fastboot 模式**，无法进入系统。
- **已提取并保存在桌面 `C:\Users\user\Desktop\ls\` 的现场诊断日志**:
  - `recovery_previous_session.log`: 记录了刷机全过程（System 18 chunks、Vendor、Boot、DTBO、vbmeta 全部以 SHA256 100% 校验成功刷入）。
  - `los24_dmesg.log`: Recovery 下抓取的内核 dmesg。
  - `los24_recovery.log`: 当前 Recovery 会话日志。

---

## 2. 核心崩溃根因深度剖析

通过挂载并解包分析已刷入的分区镜像（`system`、`vendor`、`boot`），发现了导致系统刚起跑就崩溃回 Fastboot 的两大致命致命硬伤：

### 根因一：`boot.img` 内使用的是 Android 11 旧版 First-Stage Init，无法引导 Android 17 系统
- **实测解包数据**:
  - `system` 分区：`ro.build.version.release=17`，`ro.build.version.sdk=37`（Android 17 Baklava / CinnamonBun）。其 `/system/bin/init` 是 64-bit ARM64 动态链接可执行程序，依赖 `/system/bin/bootstrap/linker64` 及 API 37 bionic libc。
  - `boot.img` 分区：内核头显示 `OS_VERSION = 11.0.0`，内核为 `4.14.357-perf+`。其 ramdisk 内包含的 `init` 二进制文件（大小 2,094,528 字节）是 **Android 11 的旧版 First-Stage Init**。
- **致命冲突机制**:
  - Android 引导流程中，Linux 内核启动后首先执行 ramdisk 中的 First-Stage Init。First-Stage Init 负责挂载 `/system`，随后通过 `execv` 切换到 `/system/bin/init selinux_setup` 和第二阶段 Init。
  - **SELinux 策略与 Treble 架构代差巨大**：Android 11 的 First-Stage Init 无法解析/编译 Android 17 的 SELinux CIL 规则（sepolicy 版本与权限类定义差异跨越了 6 个大版本），且动态链接器命名空间（Linker Namespaces）、Apex 容器挂载结构在 Android 17 中均与 Android 11 完全不同。
  - **触发 Kernel Panic**: 一旦 First-Stage Init 报错或进程 1（PID 1）崩溃退出（`SIGSEGV` 或 exit 报错），Linux 内核立即触发：
    ```text
    Kernel panic - not syncing: Attempted to kill init! exitcode=...
    ```
  - **掉入 Fastboot**: 在高通 sm6125 的 ABL（Android Bootloader）机制中，如果内核在启动数十秒内发生致命 Panic 或未向 Watchdog 喂狗，ABL 启动保护机制判定启动失败（Boot Failure / Rescue Mode），直接强制重启至 Fastboot 模式！

---

### 根因二：`fstab.qcom` 与底层文件系统格式完全不匹配（`f2fs` vs `ext4`）
- **实测解包数据**:
  - `boot.img` ramdisk 内的 `fstab.qcom` 配置：
    ```text
    /dev/block/bootdevice/by-name/userdata /data f2fs noatime,nosuid,nodev,fsync_mode=nobarrier latemount,wait,check
    ```
  - 但当前手机的 Userdata 分区（`/dev/block/sda10`）在 Recovery（PBRP）中格式化为 **`ext4`** 文件系统（通过 `mke2fs -t ext4` 格式化）。
- **致命冲突机制**:
  - Android 17 的 `fs_mgr` 解析 `fstab.qcom` 时，使用 `f2fs` 驱动强制挂载 `ext4` 分区，必然返回 `EINVAL` 错误。
  - 由于带有 `wait` 标志，`/data` 挂载失败直接导致 `init` 终止引导并触发救援保护，加速系统重启回 Fastboot。

---

### 根因三：为什么 Recovery 中看不到 `console-ramoops`？
- 在 `los24_dmesg.log` 第 181 行明确记录：
  ```text
  [    1.411623] persistent_ram: found existing invalid buffer, size 131028, start 140928
  ```
- 高通平台在崩溃重启进入 ABL/Fastboot 时，ABL 重新初始化了部分 DDR 内存头部标志，破坏了 `0x62000000` 处的 ramoops ECC 校验头，导致后续进入 Recovery 内核时检测到 buffer 无效而被清空。

---

## 3. 请 GPT 针对 LineageOS 24 (Android 17) 进行的精确修复方案

请 GPT 依据上述确凿的物理诊断数据，对 LineageOS 24 构建产物执行以下三个维度的修复：

### 任务 1：升级 `boot.img` 的 First-Stage Init 与 Ramdisk
1. **替换/更新 ramdisk `init`**:
   - 不能再打包 Android 11 的 ramdisk `init`。必须使用适配 Android 14/15/16/17 (SDK 34-37) 的 First-Stage Init 源码或通用 GKI/Treble ramdisk 二进制。
   - 确保 init 支持 Android 17 的 dynamic linker bootstrap 挂载与 SELinux 规范。
2. **内核启动参数（cmdline）宽容处理**:
   - 在 `boot.img` 的 cmdline 中显式加入 `androidboot.selinux=permissive`，避免在 Android 17 初步适配阶段因 sepolicy 拒绝导致 PID 1 崩溃。

### 任务 2：修正 `fstab.qcom` 文件系统兼容性
在 `fstab.qcom` 和 `oplus.fstab` 中，将 `/data` 挂载规则调整为支持 `ext4` 或双格式自适应：
```text
/dev/block/bootdevice/by-name/userdata /data ext4 noatime,nosuid,nodev,barrier=1 latemount,wait,check,formattable
```
或保留双条目（优先 f2fs，回退 ext4），以确保无论是 recovery 格式化的 ext4 还是原厂 f2fs 均能成功挂载。

### 任务 3：保持 AVB / VBMeta 校验禁用
确保更新包中包含的 `vbmeta.img` 继续携带 `--disable-verity --disable-verification` 标志，防止 Android 17 的 AVB 校验因 kernel / dtbo / vendor 混用触发 bootloader 锁死。

---
*本分析报告与诊断数据已同步至 GitHub 仓库：`https://github.com/hhsbjbsj/OPPO-A11x-PCHM30-LineageOS-23.2`*
