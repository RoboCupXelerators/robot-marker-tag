# robot-marker-tag

机器人顶部 **ArUco 顶标**：给外部场地相机同时解算「位置 + 朝向」。
3MF 直接用拓竹（Bambu Studio）打，附 300 dpi PNG（纸贴版）。

![preview](markers/preview_100mm.png)

## 规格

| 项 | 100 mm 版 | 80 mm 版 |
| --- | --- | --- |
| 字典 / ID | `DICT_4X4_50` / `7` | 同 |
| 模块 | 6 × 6（含 1 模块黑边） | 同 |
| 模块边长 | 16.7 mm | 13.3 mm |
| 底板 | 150 × 150 × 2 mm，圆角 R6 | 130 × 130 × 2 mm |
| 图案凸起 | 0.6 mm | 同 |
| 中心孔 | Ø3.4 mm（M3 通孔） | 同 |
| 静区 | 最窄边 1 个模块 | 同 |
| 方向 | 顶边三角凸片 = 车头 | 同 |

**图案故意偏移半个模块**：这样底板圆心正好落在白色模块中央，Ø3.4 中孔不会切到任何黑模块
（脚本会校验，若换到“中心是黑模块”的 ID 会直接报错）。

## 文件

```text
tag/aruco_4x4_50_id07_100mm.3mf    ← 拓竹直接拖进 Bambu Studio（推荐）
tag/aruco_4x4_50_id07_80mm.3mf
markers/aruco_4x4_50_id07_100mm.png ← 300 dpi，按 100 mm 打印
markers/aruco_4x4_50_id07_80mm.png
markers/manifest.json               ← 字典/ID/尺寸/孔位，解码端直接读
tools/make_tag.py                   ← 重新生成（换 ID / 尺寸 / 孔径）
```

## 打印（Bambu Studio）

1. 把 `.3mf` 拖进去 → 两个零件：`plate`（底板）和 `aruco_pattern`（黑色图案）；
2. 材料：`plate` 白、`aruco_pattern` 黑，双色打印；
3. 参数：PLA / 0.2 mm 层高 / 图案面朝上 / 无支撑；
4. 打之前可以用“按对象”看一下：**三角凸片在 +Y 边**，装配时朝车头。

打出来量一个黑模块：100 mm 版应为 **16.7 mm**，偏差 >0.5 mm 就重打或按比例缩放。

不想双色：只打 `plate`（全白），把 `markers/*.png` 100% 打到哑光相纸裁好贴上去（同样要留静区）。

## 安装

- 中孔 Ø3.4 适合 M3 螺丝：直接穿过底板拧进车顶的 M3 螺纹孔 / 螺母座；平头螺丝更贴合。
- 想用车顶热熔铜螺母（M3 外径约 4.2）：`python tools/make_tag.py --size-mm 100 --hole-mm 4.2` 重新生成。
- 双面胶也可以，但**凸片必须朝车头**，这决定了解码出来的朝向符号。
- 尽量贴在车顶平面、远离线缆遮挡，表面哑光（避免相机高光）。

## 解码（朝向）

```python
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
corners, ids, _ = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters()).detectMarkers(gray)
tl, tr, br, bl = corners[0][0]                 # 标记自身坐标系
marker_x = tr - tl; marker_y = bl - tl
heading_marker_deg = math.degrees(math.atan2(marker_y[1], marker_y[0]))
# 再用 /api/v1/field 的单应矩阵把方向转到场地坐标系
```

OpenCV 返回的角点顺序固定，所以**只要凸片朝车头**，解出的 x 轴方向就是车头方向，不需要试错。

## 多台机器人

换 ID 即可：

```bash
python tools/make_tag.py --id 8 --size-mm 100
python tools/make_tag.py --id 9 --size-mm 100
```

`manifest.json` 会随生成更新，解码端按字典+ID 区分车辆。

## 小空间方案（40 × 40 mm 上限）

**先说结论：40×40 放不下能稳定解码的 ArUco。** 相机当前有效分辨率约 **3.25 px/cm**
（2190 mm 场宽 ≈ 711 px）：

| 特征 | 物理尺寸 | 画面里的大小 | 能不能用 |
| --- | --- | --- | --- |
| ArUco 4×4（6 模块） | 40×40 mm | **13 px** | ❌ 每模块 2 px，解不出 |
| ArUco 4×4 | 80×80 mm | 26 px | ⚠️ 每模块 4.3 px，勉强 |
| ArUco 4×4 | 100×100 mm | 32 px | ✅ 推荐（每模块 5.4 px） |
| 双色长条 | 120×40 mm | 39×13 px | ✅ 两端质心定方向 |

所以 40×40 空间里应该用**不对称长条**，不要用二维码：

### `tag/feature_bar_120x40mm.3mf`（推荐）

- 120×40×2 mm 白板，前端 40×40 黑块、后端 40×20 黑条（凸起 0.6 mm）；
- 方的一端 = 车头，两端尺寸不同所以方向唯一；
- 理论朝向误差 ≈ `atan(0.5px / 19.5px)` ≈ **1.5°**（用两端黑色质心连线）；
- 如果 120 长放不下，可截到 80–100 mm，误差会升到 2–3°。

```bash
python tools/make_feature.py --shape bar     # 已生成，可直接打印
```

### `tag/feature_pad_40x40mm.3mf`（实验性）

- 44×44 板 + 20×20 黑色角三角；
- 40×40 只有 13 px，三角约 6 px，朝向误差 **10–15°**，只能粗定方向；
- 只在完全没空间、又能接受大误差时用。

```bash
python tools/make_feature.py --shape pad
```

> 如果连 120×40 也放不下，建议放弃“用标签定朝向”，改用**走一小段直线 + 相机前后位置差**算方向
> （前面试过，位置精度 1 cm 级，10 cm 位移就能把方向定到 ~5°）。

## 提手一体件（保留原孔位）

`tag/handle_129.5x40mm.3mf`：把提手加宽并兼作朝向标记，**孔位完全按原图**。

| 项 | 值 |
| --- | --- |
| 外形 | 哑铃形：中间握持段 **12 mm 宽**，两端加宽到 40 mm（各长 32.75 mm） |
| 孔位 | 孔距 **117.5 mm**，Ø3.3 通孔，距两端各 6 mm（不变） |
| 倒角 | 上下外缘 0.8 mm（约 45°，不割手） |
| 标记 | 前 20×24 黑块 + 后 12×24 黑块（凸起 0.6 mm，都在加宽垫上） |
| 方向 | **大块那一端 = 车头** |

中间 12 mm 段就是原来的握持宽度（手指能握住），加宽的只是两端放标记的垫子；
两块黑色都避开了 Ø3.3 孔，孔位、孔距完全按原图。

![handle](tag/preview_handle.png)

打印：`handle` 白 + `marker` 黑，双色；PLA、0.2mm、无支撑。
装配：沿用原来的两颗螺丝（M3×… 穿过 Ø3.3），大块朝车头。

重新生成：

```bash
python tools/make_handle.py
```
