# Vendor 迁移与环境复现资料

- `native1/`：首次原生 Vendor 派生流程的源代码、输入身份与模块定义。
- 根目录 `FIRMWARE.json`：最终实测的派生镜像身份。
- `device/oppo/PCHM30/factory-vintf/`：当前构建使用的完整 VINTF 文件。
- `reproduction/cnb/`：之前成功环境的 CNB 配置与 Dockerfile 参考。

历史 `native1/README.txt` 和 `LOCAL-VALIDATION.json` 保留当时的实验阶段说明。
当前成功包的验证范围以根目录 `TESTED-SOURCE-V2.json` 为准。不要把历史首启实验
流程自动等同于当前统一源码构建入口。

为保持公开仓库是源码与复现资料，OEM APK/JAR、内核 Image、完整分区镜像和 target-files
大包未加入 Git。原始 payload 必须由设备拥有者从已有 OEM/工程备份提供并按清单校验。
不要直接运行历史 start.sh 来替代当前根目录 build.sh；它是独立实验产品，可能修改
其历史工作目录并向原 CNB 分支提交。
