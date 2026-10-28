# PCHM30 (OPPO A11x) 顶部大黑框 (Display Cutout) 源码级彻底根治方案

### 1. 模块原理解析与黑框成因

您上传的模块中：
- **配置文件：** `module.prop` 明确写道：
  > *For OPPO A11x/PCHM30 GSI: force config_fillMainBuiltInDisplayCutout=false at every boot to remove the large black cutout fill caused by /vendor/overlay/FrameworksResTarget.apk.*
- **执行脚本：** `service.sh` 在每次开机后，通过命令行动态伪造一个运行时叠加层（Fabricated Overlay）：
  `cmd overlay fabricate --target android --name "PCHM30NoFill" android:bool/config_fillMainBuiltInDisplayCutout 0x12 0`
  将其强制覆盖为 `false`，然后强杀一次 `com.android.systemui` 生效。

**Bug 产生的物理与代码根因：**
1. OPPO A11x 的官方原厂 Vendor 分区里内置了一个 `/vendor/overlay/FrameworksResTarget.apk`。
2. 该 APK 强行将 AOSP 的配置 `config_fillMainBuiltInDisplayCutout` 设为了 `true`。
3. 在 LineageOS / 原生安卓中，一旦该配置为 `true`，`SystemUI` 的 `ScreenDecorations`（屏幕修饰层）就会把挖孔/水滴区域（350x80 像素的巨大切口）**强制用实心黑色软件图层涂黑（Software Black Fill）**，从而导致屏幕上方始终有一大块显眼的黑框遮挡通知栏与内容。

---

### 2. 如何在编译系统时“彻底编入”，永久摆脱模块？

为了在编译系统时彻底解决此问题，无需开机后再运行脚本杀进程，提供以下两套最标准的源码修改方案（推荐同时使用或优先使用**方案一**）：

---

#### 方案一（最直接彻底、100% 免疫 Vendor 覆盖）：修改 SystemUI 源码
由于 `/vendor/overlay/FrameworksResTarget.apk` 是 Vendor 分区的资源，优先级可能压过 System 基础资源，因此**直接在消费该资源的代码层强制置为 `false`** 是最一针见血、永不翻车的解法。

- **修改文件路径：**
  `frameworks/base/packages/SystemUI/src/com/android/systemui/decor/ScreenDecorations.java`
  *(或 `frameworks/base/packages/SystemUI/src/com/android/systemui/ScreenDecorations.java`，视安卓分支而定)*

- **定位方法：**
  在文件中搜索 `config_fillMainBuiltInDisplayCutout` 或 `shouldFillCutout()` 或 `mFillCutout`。

- **代码修改：**
  ```java
  // 修改前类似代码：
  private boolean shouldFillCutout() {
      return mContext.getResources().getBoolean(
              com.android.internal.R.bool.config_fillMainBuiltInDisplayCutout);
  }

  // 修改后（彻底禁用软件强制涂黑挖孔）：
  private boolean shouldFillCutout() {
      // PCHM30: Never fill cutout with black paint to avoid huge black frame
      return false;
  }
  ```
  *(注：如果代码中是变量赋值 `mFillCutout = ...`，直接改为 `mFillCutout = false;` 即可)*

**效果：**
无论底层 Vendor 怎么覆盖，SystemUI 在初始化屏幕装饰时，绝不会在屏幕顶部画任何纯黑实心矩形，从根源上彻底消灭顶部黑框！

---

#### 方案二（标准 AOSP 架构解法）：构建一个优先级更高的 Product Overlay
Android 的资源叠加优先级层级为：
`/system` < `/vendor` < `/odm` < `/oem` < `/system_ext` < `/product`
`/product` 分区的 Overlay 优先级**天然高于 `/vendor`**，因此放在 Product 分区即可完美压制 OPPO 原厂 Vendor 的错误配置。

在您的设备源码树 `device/oppo/PCHM30/` 下新建目录 `overlay-cutout/`：

1. **`device/oppo/PCHM30/overlay-cutout/Android.bp`**
   ```bp
   runtime_resource_overlay {
       name: "PCHM30DisplayCutoutOverlay",
       product_specific: true,
       sdk_version: "current",
   }
   ```

2. **`device/oppo/PCHM30/overlay-cutout/AndroidManifest.xml`**
   ```xml
   <manifest xmlns:android="http://schemas.android.com/apk/res/android"
       package="org.lineageos.overlay.pchm30.displaycutout">
       <overlay android:targetPackage="android"
                android:priority="9999"
                android:isStatic="true" />
   </manifest>
   ```

3. **`device/oppo/PCHM30/overlay-cutout/res/values/config.xml`**
   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <resources>
       <!-- Disable black painting of display cutout for OPPO A11x -->
       <bool name="config_fillMainBuiltInDisplayCutout">false</bool>
   </resources>
   ```

4. **在 `device/oppo/PCHM30/device.mk` 中加入该包：**
   ```make
   PRODUCT_PACKAGES += PCHM30DisplayCutoutOverlay
   ```

---

### 3. 给 GPT 的直接补丁修改需求提示词 (Prompt)

您可以直接将以下内容发送给 GPT：

```text
我们正在为 OPPO A11x / PCHM30 适配 LineageOS 23.2 (Android 16)。
目前屏幕顶部一直存在一个约 350x80 像素的巨型实心黑框，原因为原厂 /vendor/overlay/FrameworksResTarget.apk 将 config_fillMainBuiltInDisplayCutout 强行设为了 true，导致 SystemUI 的 ScreenDecorations 强制用黑色油漆图层涂黑切口区域。

请为我生成系统内置补丁，彻底修复该问题：
1. 在 frameworks/base/packages/SystemUI 中的 ScreenDecorations 组件中，强制将 config_fillMainBuiltInDisplayCutout 的判断结果锁死为 false（禁止任何软件层面的强制黑框填充）。
2. 在 device/oppo/PCHM30 中添加一个 product 分区的静态 RRO overlay（PRODUCT_PACKAGES += PCHM30DisplayCutoutOverlay），覆盖 android:bool/config_fillMainBuiltInDisplayCutout 为 false，以压制 vendor 分区的覆盖。
请输出具体的 diff 或代码修改位置。
```
