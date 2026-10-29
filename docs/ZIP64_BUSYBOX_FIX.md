# PCHM30 AxionOS 刷机包 Missing chunks.list / Zip64 Busybox 冲突解决方案（GPT 修复指引）

- **机型:** OPPO A11x / A9 2020 (`PCHM30` / `sm6125` / `trinket`)
- **刷机包名:** `PCHM30-AXIONOS-A16-SOURCE-TEST1-20261029T032629Z.zip`
- **文件体积:** 2,464,134,349 字节 (2.46 GB > 2.0 GiB)
- **底层报错记录:**
  ```text
  unzip: bad archive
  ERROR: Missing chunks.list
  Updater 过程结束，错误：1
  ```

---

## 一、 根本原因分析（Root Cause）

1. **Zip64 规范与 2GB 边界：**
   - 刷机包体积为 2.46GB，超过了经典 Zip 格式的 2^31-1（2GB）边界，Zip 压缩器自动使用了 **Zip64 扩展**。
2. **BusyBox 的 unzip 不支持 Zip64：**
   - `update-binary` 脚本中使用了：
     ```bash
     for file in chunks.list partition-sizes.list final-files.list; do
         "$BB" unzip -p "$ZIP" "$file" > "$TMP/$file" || abort "Missing $file"
     done
     ```
     其中 `$BB` 为 `/sbin/busybox`。
   - BusyBox 的 `unzip` 源码未开启 Zip64 支持或为 32 位偏移量实现，遇到 Zip64 归档直接输出 `unzip: bad archive` 并返回非 0 退出码，触发了 `|| abort "Missing $file"`。
3. **Recovery 原生 unzip 完美支持 Zip64：**
   - 经真机测试，Recovery 自身的 `/system/bin/unzip`（Android ziptool）能够 100% 正常读取、解压和流式校验该 2.46GB 刷机包的所有分块文件。

---

## 二、 修复方案（请 GPT 在打包脚本与 update-binary 中采纳）

在生成 `update-binary` 模板时，解压工具定义必须优先使用 Android 系统的原生 `unzip`，避免死板绑定到 BusyBox：

### 1. 修改解压器探测逻辑（置于 update-binary 头部）
```bash
BB=
for candidate in /sbin/busybox /system/bin/busybox /system/xbin/busybox; do [ ! -x "$candidate" ] || { BB=$candidate; break; }; done
[ -n "$BB" ] || abort 'PBRP busybox required; no partitions were written.'

# 优先选用原生支持 Zip64 (>2GB) 的系统 unzip
UNZIP=
if [ -x /system/bin/unzip ]; then
    UNZIP="/system/bin/unzip"
elif [ -x /system/xbin/unzip ]; then
    UNZIP="/system/xbin/unzip"
elif command -v unzip >/dev/null 2>&1; then
    UNZIP="unzip"
else
    UNZIP="$BB unzip"
fi
```

### 2. 将所有 `"$BB" unzip` 替换为 `"$UNZIP"`
- 读取元数据列表：
  ```bash
  for file in chunks.list partition-sizes.list final-files.list; do
      "$UNZIP" -p "$ZIP" "$file" > "$TMP/$file" || abort "Missing $file"
  done
  ```
- 预校验分块 SHA256：
  ```bash
  actual=$("$UNZIP" -p "$ZIP" "$member" | "$BB" sha256sum) || abort "Cannot hash $member"
  bytes=$("$UNZIP" -p "$ZIP" "$member" | "$BB" wc -c) || abort 'Cannot count chunk bytes.'
  ```
- 写入目标分区：
  ```bash
  "$UNZIP" -p "$ZIP" "$member" | "$BB" dd of="$BASE/$part" bs=4096 seek="$offset" conv=notrunc || abort "Write failed: $part. Remain in Recovery."
  ```

采纳此修改后，刷机包体积超过 2GB 时将不再报 `ERROR: Missing chunks.list`。
