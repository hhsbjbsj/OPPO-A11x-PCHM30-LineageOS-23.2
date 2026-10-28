# Vendor / 固件复现输入

当前 Device 使用完整实测 Vendor 镜像作为预编译输入，OEM HAL 并非公开源码重建。
这里不放置 `.img`、APK、JAR、个人分区或平台私钥。

## 推荐复现路径

1. 准备独立附件 `PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip`。
2. 在已预装 `/opt/lineage` 的 CNB 中，运行根目录 `build.sh --modules` 或 `--system`。
3. `tools/setup.py` 核验 ZIP 内四个镜像的大小和 SHA256，将真实文件放到
   `/opt/lineage/vendor/oppo/pchm30-tested-firmware/`。Soong 不引用源码树外的绝对预编译路径。

确切 Vendor、boot、DTBO、vbmeta 校验值与内核来源在根目录 `FIRMWARE.json`。
原有固件附件 ZIP 的 SHA256 为：

```text
1368a8f2756a084e46229f7f539d2f9dd0ae34695eb084a77aadda5d414e4c8b
```

固件可由用户从已有本地备份提供。CNB 的上传目标为 `Anyin123f/recovery` 中
`pchm30-los23.2-source-v2-cutout-fixed` 对应 Release；是否已上传成功应以固化回执和
远端附件为准，本仓库不将待上传的附件描述为已在线。

## 原厂 Vendor 派生过程

`vendor/reproduction/native1/` 保存原生迁移脚本、设备模块定义、输入校验、
应用与接口清单以及 Run140 内核集成脚本。流程从已有工程 target-files 与 OEM
APK/JAR 输入出发，经当前平台 ART / ARM64 dexpreopt 校验、平台签名迁移和设备矩阵派生。
它不向 Android16 虚报支持整个 System SDK28。

这些历史流程需要原始备份、OEM payload 和对应工具，不是仅凭本公开仓库就能从零
编译闭源硬件库。优先复用上述按哈希锁定的实测固件；切换平台签名时必须重新处理
Vendor Java 服务签名。嵌套 ODM 保留在 Vendor 内，不能将其刷到较小的物理 ODM 分区。
