# CNB 环境记录

这里保留原 CNB `los` 分支的配置和带同步进度输出的 Dockerfile，来源于之前固化的
成功环境记录。构建镜像需要首次获取 Android 源码；当前 IDE 内的根目录 build.sh
只复用 `/opt/lineage`，不会重新 repo sync。

Dockerfile 中的官方 manifest 提交与 VNDK30 提交已固定，但其中的上游分支引用
可能随时间改变。严格重建应以根目录 `default.xml` 的全项目提交锁定为准，并在
应用补丁前通过 tools/apply.py 的项目和文件校验。实际新环境构建仍需独立验证。

不要把这份环境记录直接覆盖其他系统的 `.cnb.yml`；为衍生系统使用独立分支。
