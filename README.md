# robot-marker-tag

机器人顶部 **ArUco 顶标**，给外部场地相机同时解算「位置 + 朝向」用。
现成的 3MF（拓竹 / Bambu Studio 直接导入）+ 300 dpi PNG（纸质打印）。

## 规格

| 项 | 值 |
| --- | --- |
| 字典 | `DICT_4X4_50` |
| ID | `7` |
| 模块 | 6 × 6（含 1 模块黑边） |
| 尺寸 | 100 mm（主用）/ 80 mm（紧凑） |
| 模块边长 | 16.67 mm / 13.33 mm |
| 底板 | 2.0 mm 厚，四周留 20 mm 白边（>1 模块静区） |
| 图案凸起 | 0.6 mm |
| 车头方向 | 底板 **凸片** 那一侧朝车头 |

为什么用 4×4：相机在 3.5 m 处，10 cm 标签约 30–45 px，6 个模块 → 每模块 5–7 px，
`4x4` 仍能稳定解码；再大的字典（5×5/6×6）同样像素下更容易失败。

## 文件

```text
tag/aruco_4x4_50_id07_100mm.3mf    ← 拓竹直接拖进 Bambu Studio
tag/aruco_4x4_50_id07_80mm.3mf
markers/aruco_4x4_50_id07_100mm.png ← 300 dpi，按 100 mm 打印
markers/aruco_4x4_50_id07_80mm.png
markers/manifest.json               ← 字典/ID/尺寸，给解码端读
tools/make_tag.py                   ← 重新生成（改 ID / 尺寸）
```

## 打印（Bambu Studio）

1. 把 `.3mf` 拖进 Bambu Studio，会看到两个零件：`plate` 和 `aruco_pattern`；
2. 材料分配：`plate` → 白色，`aruco_pattern` → 黑色（双色打印，图案凸起 0.6 mm）；
3. 参数：PLA / 0.2 mm 层高 / 无支撑 / 图案面朝上；底板开不开 brim 都行；
4. 打出来用卡尺量一个黑色模块：应为 **16.7 mm**（100 mm 版），偏差 >0.5 mm 就重打或缩放。

不想双色打印也行：打全白的 `plate`，把 `markers/*.png` 按 100% 打到哑光相纸上，裁好贴上去。

## 安装

- 用双面胶/魔术贴固定在机器人顶部**平面**，居中；
- **底板凸片朝车头**（决定解码出来的朝向符号）；
- 贴的时候抬高一点避开线缆，保证从上方看图案不被遮挡、不反光（哑光更好）。

## 解码

```python
import cv2
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
corners, ids, _ = det.detectMarkers(gray)
```

OpenCV 返回的 `corners` 顺序是 左上、右上、右下、左下（标记自身的坐标系），
所以朝向可以直接从角点算：

```python
tl, tr, br, bl = corners[0][0]
x_m = tr - tl; y_m = bl - tl                 # 标记 +x / +y
heading_marker = math.degrees(math.atan2(y_m[1], y_m[0]))
# 再叠加到场地标定（/api/v1/field 的单应矩阵）即可得到场地坐标系里的朝向
```

字段 `manifest.json` 里给了字典/ID/尺寸，解码端不用改代码就能换尺寸。

## 重新生成

```bash
python tools/make_tag.py --dict 4x4_50 --id 7 --size-mm 100
python tools/make_tag.py --dict 4x4_50 --id 8 --size-mm 100   # 另一台机器人换 ID
```

多台机器人用不同 ID（7、8、9…），避免相机混淆。

![tag preview](markers/preview_100mm.png)
