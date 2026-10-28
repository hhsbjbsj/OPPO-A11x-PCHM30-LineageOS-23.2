# PCHM30 LOS23.2 修改记录

本记录对应 Android 16 / LineageOS 23.2 原生源码构建。当前重建入口为根目录
`build.sh`，统一补丁为 `patches/`。`history/diagnostic-patches/` 中的旧补丁保留定位过程，
不需要在统一补丁之后再次应用。

| 阶段 | 原故障与最终处理 | 当前源码归属 |
| --- | --- | --- |
| Stage1 / DIAG1 | 老内核触发 netbpfload 版本门槛与失败重启；保留实测版本覆盖属性，取消失败重启，保留真实加载错误 | Device 属性、Connectivity loader rc |
| Stage2 | netd 重启触发 zygote 反复重启 | system/netd/server/netd.rc |
| Stage3 | netd updatable 因缺失 BPF 程序主动 abort | Connectivity/bpf/netd/NetdUpdatable.cpp |
| Stage4 | 带宽规则初始化失败退出 netd | system/netd/server/Controllers.cpp，保留后续 Route/Xfrm 检查 |
| Stage5 | DNS ADnsHelper 初始化失败主动退出 | DnsResolver/DnsProxyListener.cpp，已有空回调分支 |
| Stage6 | CLAT BPF 检查致命退出 | Connectivity JNI，保留真实 JNI 注册 |
| Stage7 | Java BPF map 初始化失败、空 map 访问 | BpfNetMaps、BpfNetMapsUtils、NetworkStackBpfNetMaps、NetworkStats 等 |
| Stage8 → Stage9 | 先定位 RANGING / AppOp 151，再统一处理缺失权限定义的映射 | frameworks/base AppOpService.kt；Stage8 单点处理已由通用逻辑替代 |
| Stage10 | 缺少 BPF 时统计读取 IOException 继续打断 system_server | NetworkStatsFactory / NetworkStatsService；日志明确标记统计不可用 |
| Stage11 | 三个已声明特权权限被特性开关隐藏 | frameworks/base AndroidManifest.xml，仅移除对应 featureFlag，保留 protectionLevel |
| Stage12 | lmkd 等待 BPF memevents，阻塞后触发框架 watchdog | lmkd.cpp，进入已有 vmstats 降级路径 |
| VNDK30 | 原厂 Android 11 vendor 需要旧 VNDK runtime | 恢复 com.android.vndk.v30 APEX 并纳入 System |
| Vendor 原生迁移 | 5 个旧 Vendor APK、15 个 ODM 接口 JAR 与旧 System SDK28 合约 | 原生 android_app_import / dex_import、平台签名迁移、派生设备矩阵；流程见 vendor/reproduction |
| SystemUI 切口 | 厂商 overlay 开启切口填黑产生顶部黑框 | ScreenDecorations、DisplayCutoutBaseView、CutoutDecorProviderFactory 共 3 文件固定关闭填充 |
| 构建修复 | Soong 扫描源码树里的备份 Android.bp，产生重复模块 | 备份移出源码树，跨文件系统搬移、重复执行与内容保留均有测试 |
| 固化 | 保存当前成功源码、环境、镜像身份及附件 | tools/freeze_cnb.py；旧标签保留，附件与源码提交分开核验 |

## 版本与验证

- 上游 6 个补丁项目及精确提交：`SOURCE-INPUTS.json`。
- 全平台锁定的 1165 项目：`default.xml`。
- 当前 19 个修改文件的前后 SHA256：`PATCHSET.json`。
- 核心模块构建输出：`CNB-MODULE-BUILD.json`。
- 包含切口修复的原生整包：`TESTED-SOURCE-V2.json`。
- 用户反馈：新包刷入成功，使用正常。没有把此反馈扩写为所有硬件功能完整测试。
- 旧的二进制修改版与新的源码构建版分开记录；历史诊断报告保留当时的时间和验证范围。

## 保留的限制

当前是针对 4.14 设备的特定 bring-up 基线。缺失的 BPF 后端没有因此实现；
流量统计、网络策略、Data Saver 等存在降级。版本覆盖属性不代表内核升级。
严格内核 FCM 检查尚未通过，vbmeta flags=3 与平台测试证书沿用实测输入。
切口填充开关控制的相机保护遮罩也关闭。换平台、签名或内核后须重新适配和实测。
