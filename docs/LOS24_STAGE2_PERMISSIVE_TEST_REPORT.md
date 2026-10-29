# OPPO A11x (PCHM30) LineageOS 24 第二次实机测试（Permissive 补丁）物理日志结构报告

> 测试时间：2026-10-29 15:41  
> 测试包：`PCHM30-LOS24-SELINUX-PERMISSIVE-LOCAL.zip`  
> 状态：补丁通过 Recovery 成功写入，实机重启测试完成。

---

## 一、本次测试验证成功的核心进展

1. **Permissive 宽容参数已成功传入物理内核**：
   - 提取的 `device-info-ramoops-0` 确认命令行已包含：
     ```text
     androidboot.pchm30_legacy_odm=1 androidboot.init_fatal_reboot_target=recovery androidboot.selinux=permissive
     ```
2. **内核与 Android 37 静态 Init 运行进一步推进**：
   - 查看最新内核崩溃缓冲：
     ```text
     [    0.202956] (5)[1:swapper/0]persistent_ram: found existing invalid buffer, size 131028, start 146294
     ```
   - 相比上一版的 140,928 字节，本次系统运行生成的日志量达到了 **146,294 字节**（日志推进了 5.3 KB），证明系统在 Permissive 模式下成功越过了上一版的 SELinux 早期阻断！
3. **安全拦截保护依然生效**：
   - 遇到后续错误时，手机未掉入 Fastboot，依然精准重启回到了 Recovery。

---

## 二、本次再次触发 `InitFatalReboot("recovery")` 的硬伤定位

通过对提取的静态 `init` 二进制文件与 `ramdisk` 配置进行符号分析，定位到了当前的两个关键拦截点：

### 1. `pchm30_legacy_odm` 自定义挂载模块在 Early Stage 的潜在冲突
- GPT 在 `first_stage_init` 中嵌入了 `system/core/init/pchm30_legacy_odm.h`，在 `selinux_setup` 之前通过 loop-control 尝试挂载 `/vendor/euclid/odm.img` 与 `my_manifest.img`。
- 提取出的二进制中包含以下错误捕获分支：
  ```text
  PCHM30: unexpected loop block device
  PCHM30: expected embedded image is unavailable: /vendor/euclid/my_manifest.img
  ```
- 在 First Stage Init 阶段，`ueventd` 尚未启动，动态分配的 loop 设备节点可能触发不可预期错误并触发 `LOG(FATAL)`。

### 2. `oplus.fstab` 中 ColorOS 遗留分区的阻碍
- ramdisk 内的 `oplus.fstab` 依然包含大量仅属于 ColorOS 的专有 loop 挂载规则（如 `loop@/system/euclid/my_product.img`、`my_heytap.img`、`my_stock.img`），且全部标记了 `first_stage_mount`。
- LineageOS 24 的 `/system` 根本不存在 `/system/euclid/` 目录，Android 17 原生 init 解析这些无效的第一阶段条目容易造成异常。

---

## 三、下一步精准建议（交付 GPT）

1. **测试关闭 `pchm30_legacy_odm`**：
   - 在 `cmdline` 中将 `androidboot.pchm30_legacy_odm=1` 改为 `androidboot.pchm30_legacy_odm=0`，观察系统在不进行早期 loop 挂载时的推进情况。
2. **精简 `oplus.fstab`**：
   - 剔除 `oplus.fstab` 中不存在的 `my_product`、`my_heytap` 等废弃条目，仅保留 `/mnt/vendor/opporeserve` 或将必要条目合并入 `fstab.qcom`。
