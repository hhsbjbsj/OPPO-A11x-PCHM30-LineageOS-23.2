PCHM30 LOS23.2 原厂派生 vendor / 首次完整安装候选包

先上传 LOS23.2-BACKUP-target-files.zip 到 /workspace，再解压并运行本目录 start.sh。
不需要另外上传原厂输入包，不进行 repo sync，不重新构建 systemimage。
会编译五个 android_app_import 原生模块、15个 ODM dex_import 接口库、对应 dexpreopt 依赖和主机工具；缓存丢失后这一步仍可能需要较长时间。

本包采用独立的 lineage_PCHM30_vendorport 产品构建五个服务，不再自行猜测 dexpreopt JSON 结构。
将五个 APK 用已编译系统的同一平台密钥签名；要求 native ARM64 dexpreopt 产物存在，签名完整验证通过，解压后的 APK 内容保持一致。
不把新产品的 odex/vdex 混入旧 system：清除原厂应用旧的预优化文件，保留签名后的完整 DEX，由目标系统自行处理。

Vendor 合约变更明确说明：
这不是在 Android16 中补回整个 SystemSDK28，也不是让 framework 虚报支持28。
只有五个 vendor 应用和15个 ODM 接口库经过当前平台原生 ART 构建流程、应用签名迁移完成后，才用原生构建生成的新 device compatibility matrix 取代原厂的 SDK28 合约。
保留原厂 VNDK30、硬件 blobs、嵌套 ODM 和内核。生成的 vendor 合约不能证明 JNI、Binder、权限及全部硬件运行行为已经通过。
依然是首次启动候选版本，不是已通过实机测试的稳定 ROM。

System 仅修改先前已识别的三个旧 HAL 实例声明；不重建系统应用、不添加假的 SDK28 支持。
对生成镜像检查 ext4、AVB、实际 DSDS/SSSS VINTF 和 SELinux 运行期链接。跨版本 neverallow 额外审查的结果保留在报告中，未解决时不得宣称严格策略适配完成。
任一强制检查失败都保留报告并停止，不制作安装候选 ZIP。

成功输出：/workspace/DOWNLOAD-ROM-VENDOR-NATIVE1/PCHM30-LOS23.2-VENDOR-NATIVE1-时间.zip
另有派生 vendor.img、报告与 SHA256。安装 ZIP 本身包含 system/vendor/boot/dtbo/vbmeta。
安装器核对真实分区映射、大小以及所有数据块，然后写入并回读校验。
不写 GPT、物理 ODM、recovery、userdata，不格式化数据，也不自动重启。
旧系统数据的跨版本启动和解密仍未验证；生成 ZIP 不代表手机一定能开机。

运行 start.sh 不会刷机。不要把工程 target-files.zip 当作刷机 ZIP。
本套脚本尚未在 CNB 执行；本地验证只证明解析、输入校验、矩阵合并和归档规则，不能声称 Linux 原生构建或手机启动已通过。

原生模块依据：
https://github.com/LineageOS/android_build_soong/blob/lineage-23.2/java/app_import.go
https://github.com/LineageOS/android_build_soong/blob/lineage-23.2/java/java.go
https://github.com/LineageOS/android_build_soong/blob/lineage-23.2/java/dexpreopt.go
参考 vendor 组合方式：
https://github.com/LineageOS/android_device_xiaomi_sm6125-common/blob/lineage-23.2/common.mk
