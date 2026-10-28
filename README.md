# OPPO PCHM30 · LineageOS 23.2 源码实测基线 V2

这是为 OPPO A11x/PCHM30 整理的 Android 16 / LOS 23.2 **源码修复集**。
与先前从手机备份的可用镜像不同，本仓库修改上游 C++、Java、Kotlin、清单和 init
源码，再让 Android 构建系统生成 services.jar、framework-res、netd、lmkd 和 APEX。
**不使用固定地址二进制补丁、SMALI 补丁或预先打好的核心框架文件。**

当前状态：6 个源码项目、19 个修改文件，包含 SystemUI 切口填黑修复。
此前 16 个文件通过精确补丁应用/重复执行/源码漂移检查，
所有修改 Java 文件通过语法树解析，三个实际统计方法通过 javac 和 24 个运行案例。
2026-10-28 的 CNB 核心模块构建已通过（20 分 44 秒），构建后的 6 项目、16 文件
源码检查也全部通过。目标为 `services`、`framework-res`、`netd`、`lmkd`、
`com.android.tethering` 和 `com.android.resolv`；记录见 `CNB-MODULE-BUILD.json`。
完整 System 和整包已在 CNB 构建。用户已刷入包含切口修复的新包并反馈使用正常。
确切镜像与文件校验值见 `TESTED-SOURCE-V2.json`；此反馈不代表所有硬件功能都已逐项测试。
V2 新增的 3 个 SystemUI 源码文件已纳入统一补丁，重建时不需要单独再应用切口补丁。
先前手机上可用的镜像和 CNB 标签 `pchm30-los23.2-stage12-v1` 保持不变。

## 修复范围

| 源码项目 | 内容 |
| --- | --- |
| packages/modules/Connectivity | loader 失败时取消重启；netd updatable 初始化降级；CLAT 保留日志并继续 JNI 注册；Java map 初始化/空值保护；无统计时返回有告警的空快照 |
| system/netd | 取消 netd 重启连带杀 zygote；带宽初始化失败仍继续后续 Route/Xfrm 检查 |
| packages/modules/DnsResolver | ADnsHelper 初始化失败使用已有空回调路径 |
| frameworks/base | 通用跳过缺失权限定义的 AppOp 映射；恢复三个已声明且已白名单允许的特权权限定义，保持原保护等级 |
| system/memory/lmkd | 使用现有 vmstats 分支，不无限等待 BPF 内存事件；保留 PSI/普通内存压力/OOM/socket 逻辑 |
| packages/modules/vndk | 构建并安装与原厂 vendor 对应的 VNDK 30 APEX |

设备配置同时保留 `ro.bpf.kver_override=5.10.239`，与实测 bring-up 基线一致。
SystemUI 的三个切口填充入口固定关闭；切口布局和圆角仍保留，同一开关控制的相机保护遮罩也关闭。
不伪造 `bpf.progs_loaded=1`。本修复集不是完整 BPF 后端，流量统计、网络防火墙、
Data Saver 等仍存在降级。内核严格 FCM 验证限制和 vbmeta flags=3 仍保留。

## 在当前 CNB 只应用源码补丁

将源码 ZIP 解压到 `/workspace/pchm30-los-source-baseline` 后：

```bash
python3 /workspace/pchm30-los-source-baseline/tools/apply.py --root /opt/lineage --apply
```

默认校验锁定的项目提交和全部目标文件 SHA256。所有项目预检查完成后才改源码；
原文件备份到源码树之外：CNB 默认使用 `/workspace/artifacts/pchm30-source-baseline-backups/lineage/`。
旧版在源码树内创建的 `.pchm30-source-baseline-backups/` 会自动搬到该目录保留，避免
备份中的 `Android.bp` 被 Soong 扫描而重复定义模块。可用 `PCHM30_SOURCE_BACKUP_ROOT`
指定其他树外目录。重复执行会跳过已应用
项目。遇到不匹配源码会停止，不强推、不重置、不下载源码、不刷手机。

## 在当前 CNB 编译验证

还需要 `PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip`，它是当前已实测的 boot/vendor/DTBO/
vbmeta 输入，**不含 System、services.jar 或核心 APEX**。此设备的内核和 OEM HAL
仍作为预编译固件输入使用；“源码修复”不等于 OEM vendor 和内核也全由本仓库编译。
`FIRMWARE.json` 锁定其版本和校验值。该附件单独保存，不加入源码 Git 历史。

```bash
cd /workspace/pchm30-los-source-baseline
bash build.sh --modules /workspace/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip
```

这会准备 ROM 设备树和已核验固件，应用源码补丁，使用现有 `/opt/lineage` 缓存，
以 64 线程编译核心模块。不会 `repo sync`，不会自动刷机。完整系统和单 ZIP：

```bash
bash build.sh --system /workspace/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip
```

新候选位于 `/workspace/DOWNLOAD-ROM-SOURCE-BASELINE/`；System 来自本次原生构建，
其余四个分区来自核验过的固件输入。安装器检查分区映射、大小、每个镜像块和最终
文件，保留 GPT、Recovery、物理 ODM 与 Data。新源码构建需重新上机测试，不能
把之前二进制版本的实测结果自动当作它已通过测试。

## 当前 CNB 固化

保持实测成功的 ZIP、现有固件 ZIP 和 `/opt/lineage` 构建输出存在，在下载的固化包目录运行：

```bash
python3 tools/freeze_cnb.py
```

脚本会核验确切 ZIP、19 个补丁文件及包括 SystemUI 的 9 个实际构建文件，
把源码、设备配置和现场 manifest 保存到 CNB `los` 分支的
`stable/pchm30-los23.2-source-v2/`，建立新标签 `pchm30-los23.2-source-v2-cutout-fixed`。
整包、固件、完整源码归档和 SHA256SUMS 使用当前 CNB IDE 的内置令牌上传为长期 Release 附件；
令牌不写入源码、输出或归档。代码提交与附件上传分别核验，部分失败不会报告全部固化成功。
不会修改当前分支或已有暂存内容，不会强推、覆盖旧标签、重编、刷机或停止工作空间。
首次固化请使用对应固化包；同名稳定标签创建后，不用后续更新的 GitHub main 覆盖旧归档。
今后可用 `bash stable/pchm30-los23.2-source-v2/source/build.sh --system /workspace/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip` 重建。

## 从 GitHub 获取基线

公开仓库：<https://github.com/hhsbjbsj/OPPO-A11x-PCHM30-LineageOS-23.2>，分支 `main`。

```bash
git clone --branch main https://github.com/hhsbjbsj/OPPO-A11x-PCHM30-LineageOS-23.2.git pchm30-los-source-baseline
cd pchm30-los-source-baseline
bash build.sh --modules /workspace/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip
bash build.sh --system /workspace/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip
```

以上命令使用当前 CNB 的 `/opt/lineage` 缓存，不自动刷机。
独立固件附件需由原有本地文件或已经确认上传成功的 CNB Release 提供；本次提交不含
`.img`、APK/JAR payload、大刷机包或个人 Data。Vendor 输入与复现说明见
`vendor/oppo/pchm30-tested-firmware/README.md`，迁移流程见 `vendor/reproduction/`。
全部阶段的修改说明见 `docs/CHANGELOG.md`，早期诊断补丁见 `history/diagnostic-patches/`。

已有 CNB 缓存时只克隆本仓库再运行上述脚本，不会重新下载 Android 源码。
在完全新环境要同步基线时，本仓库提供锁定 1165 项目的 `default.xml`：

```bash
repo init -u https://github.com/hhsbjbsj/OPPO-A11x-PCHM30-LineageOS-23.2.git -b main --git-lfs
repo sync -c -j16 --no-clone-bundle --no-tags
python3 .repo/manifests/tools/setup.py --root "$PWD" --firmware /path/to/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip
```

首次空环境同步必然需要获取上游源码；这与在当前 CNB IDE 复用预装源码缓存是两种
情况。构建脚本默认 CNB 目录布局；其他机器应调整 `ANDROID_BUILD_TOP` 和输出目录。

## 基于其他 LOS 衍生系统

保留本分支作为基线，另开分支修改平台 manifest，再逐项目移植源码补丁并重新编译、
检查 VINTF/SELinux/权限、测试设备。默认版本校验会拦截不同平台提交；不要用“强行
跳过”替代移植。若确实只有提交历史不同且全部目标文件完全相同，可明确使用
`--accept-file-identical-head`，仍会逐文件校验，不接受任意内容。

测试固件中迁移的 vendor Java 应用按现有 AOSP 平台测试证书签名。切换衍生系统或
私有签名后，需要相应重新处理 vendor 模块签名，不能假定签名兼容。

内核来源：hhsbjbsj/android_kernel_oppo_sm6125-resukisu-final，实测 Run140 提交
`190a49ea435d04c3d9f1974dfcb6c53334fa3524`。当前仓库使用对应已实测 boot 输入。
所有补丁的精确上游项目和提交见 `SOURCE-INPUTS.json`，文件哈希见 `PATCHSET.json`。
