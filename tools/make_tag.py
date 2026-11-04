"""生成 ArUco 顶标：PNG（精确尺寸）+ Bambu 可用的双色 3MF（毫米单位）。

用法：python tools/make_tag.py --dict 4x4_50 --id 7 --size-mm 100
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DICTS = {
    "4x4_50": cv2.aruco.DICT_4X4_50,
    "5x5_100": cv2.aruco.DICT_5X5_100,
    "6x6_250": cv2.aruco.DICT_6X6_250,
    "apriltag_36h11": cv2.aruco.DICT_APRILTAG_36h11,
}
MODULES = {"4x4_50": 4, "5x5_100": 5, "6x6_250": 6, "apriltag_36h11": 6}


def marker_bits(name: str, marker_id: int) -> np.ndarray:
    """返回 (N+2)x(N+2) 布尔矩阵，True=黑模块（含 1 模块黑边）。"""
    dictionary = cv2.aruco.getPredefinedDictionary(DICTS[name])
    n = MODULES[name]
    side_px = (n + 2) * 40
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px, 1)
    return (img.reshape(n + 2, 40, n + 2, 40).mean(axis=(1, 3)) < 128)


def save_png(bits: np.ndarray, size_mm: float, out: Path) -> None:
    n = bits.shape[0]
    px = int(round(size_mm / 25.4 * 300))          # 300 dpi
    px -= px % n
    img = np.where(bits, 0, 255).astype(np.uint8)
    img = cv2.resize(img, (px, px), interpolation=cv2.INTER_NEAREST)
    img = cv2.copyMakeBorder(img, px // 8, px // 8, px // 8, px // 8,
                             cv2.BORDER_CONSTANT, value=255)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)


def _box(x0, y0, z0, x1, y1, z1, vertices, triangles):
    i = len(vertices)
    vertices += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                 (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    for tri in ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
                (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
                (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)):
        triangles.append(tuple(i + k for k in tri))


def save_3mf(bits: np.ndarray, size_mm: float, out: Path,
             plate_margin_mm: float = 20.0, plate_mm: float = 2.0,
             relief_mm: float = 0.6) -> None:
    n = bits.shape[0]
    module = size_mm / n
    total = size_mm + 2 * plate_margin_mm
    base_v, base_t = [], []
    _box(-total / 2, -total / 2, 0.0, total / 2, total / 2, plate_mm, base_v, base_t)
    # 车头指示凸片：贴 +Y 边，装机时凸片朝车头
    tab_w, tab_h = 24.0, 10.0
    _box(-tab_w / 2, total / 2, 0.0, tab_w / 2, total / 2 + tab_h, plate_mm, base_v, base_t)
    pat_v, pat_t = [], []
    for row in range(n):
        for col in range(n):
            if not bits[row, col]:
                continue
            x0 = -size_mm / 2 + col * module
            y0 = -size_mm / 2 + (n - 1 - row) * module
            _box(x0, y0, plate_mm, x0 + module, y0 + module, plate_mm + relief_mm, pat_v, pat_t)
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <metadata name="Title">Xelerator ArUco top tag</metadata>
 <metadata name="Designer">RoboCupXelerators</metadata>
 <resources>
  <object id="1" type="model" name="plate">
   <mesh><vertices>{''.join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in base_v)}</vertices>
   <triangles>{''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in base_t)}</triangles></mesh>
  </object>
  <object id="2" type="model" name="aruco_pattern">
   <mesh><vertices>{''.join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in pat_v)}</vertices>
   <triangles>{''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in pat_t)}</triangles></mesh>
  </object>
 </resources>
 <build><item objectid="1"/><item objectid="2"/></build>
</model>
'''
    types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
'''
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default="4x4_50", choices=sorted(DICTS))
    ap.add_argument("--id", type=int, default=7)
    ap.add_argument("--size-mm", type=float, default=100.0)
    ap.add_argument("--plate-margin-mm", type=float, default=20.0)
    args = ap.parse_args()
    bits = marker_bits(args.dict, args.id)
    n = bits.shape[0]
    module_mm = args.size_mm / n
    stem = f"aruco_{args.dict}_id{args.id:02d}"
    save_png(bits, args.size_mm, ROOT / "markers" / f"{stem}_{int(args.size_mm)}mm.png")
    save_3mf(bits, args.size_mm, ROOT / "tag" / f"{stem}_{int(args.size_mm)}mm.3mf",
             plate_margin_mm=args.plate_margin_mm)
    manifest = {
        "dictionary": args.dict, "id": args.id, "size_mm": args.size_mm,
        "modules": n, "module_mm": round(module_mm, 2),
        "quiet_zone_module": True, "plate_margin_mm": args.plate_margin_mm,
        "relief_mm": 0.6, "plate_mm": 2.0,
    }
    (ROOT / "markers" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
