"""生成 ArUco 顶标：PNG（精确尺寸）+ Bambu 可用 3MF（毫米、圆角、中心 M3 孔、车头凸片）。

用法：
    python tools/make_tag.py --dict 4x4_50 --id 7 --size-mm 100
    python tools/make_tag.py --size-mm 100 --hole-mm 0     # 不要中孔
"""

from __future__ import annotations

import argparse
import json
import math
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
PLATE_MM = 2.0
RELIEF_MM = 0.6
CORNER_R_MM = 6.0


def marker_bits(name: str, marker_id: int) -> np.ndarray:
    """(N+2)x(N+2) 布尔矩阵，True=黑模块（含 1 模块黑边）。"""
    dictionary = cv2.aruco.getPredefinedDictionary(DICTS[name])
    n = MODULES[name]
    side = (n + 2) * 40
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, side, 1)
    return (img.reshape(n + 2, 40, n + 2, 40).mean(axis=(1, 3)) < 128)


def save_png(bits: np.ndarray, size_mm: float, out: Path) -> None:
    n = bits.shape[0]
    px = int(round(size_mm / 25.4 * 300))
    px -= px % n
    img = np.where(bits, 0, 255).astype(np.uint8)
    img = cv2.resize(img, (px, px), interpolation=cv2.INTER_NEAREST)
    pad = px // 8
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)


# --------------------------------------------------------------------------- mesh


class Mesh:
    def __init__(self):
        self.vertices: list[tuple[float, float, float]] = []
        self.triangles: list[tuple[int, int, int]] = []

    def add_box(self, x0, y0, z0, x1, y1, z1):
        i = len(self.vertices)
        self.vertices += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                          (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for tri in ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
                    (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
                    (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)):
            self.triangles.append(tuple(i + k for k in tri))

    def add_prism(self, polygon, z0, z1):
        """凸多边形向上挤出（顶/底扇形三角化 + 侧壁）。"""
        n = len(polygon)
        base = len(self.vertices)
        for z in (z0, z1):
            for x, y in polygon:
                self.vertices.append((x, y, z))
        cx = sum(p[0] for p in polygon) / n
        cy = sum(p[1] for p in polygon) / n
        cb = len(self.vertices); self.vertices.append((cx, cy, z0))
        ct = len(self.vertices); self.vertices.append((cx, cy, z1))
        for i in range(n):
            j = (i + 1) % n
            self.triangles.append((cb, base + j, base + i))            # bottom (-Z)
            self.triangles.append((ct, base + n + i, base + n + j))    # top (+Z)
            self.triangles += [(base + i, base + j, base + n + j),
                               (base + i, base + n + j, base + n + i)]
        return base


def _rounded_rect_half(a: float, b: float, r: float, angle: float) -> float:
    """从中心沿 angle 射线到圆角矩形边界的距离。"""
    dx, dy = math.cos(angle), math.sin(angle)
    lo, hi = 0.0, a + b
    for _ in range(60):
        t = (lo + hi) / 2
        x, y = t * dx, t * dy
        qx = abs(x) - (a - r); qy = abs(y) - (b - r)
        d = math.hypot(max(qx, 0.0), max(qy, 0.0))
        if d <= r:
            lo = t
        else:
            hi = t
    return lo


def _plate_with_hole(mesh: Mesh, half: float, r_corner: float, hole_r: float,
                     z0: float, z1: float, segments: int = 96):
    inner_top, inner_bot, outer_top, outer_bot = [], [], [], []
    for k in range(segments):
        ang = 2 * math.pi * k / segments
        ro = _rounded_rect_half(half, half, r_corner, ang)
        ca, sa = math.cos(ang), math.sin(ang)
        inner_top.append((hole_r * ca, hole_r * sa, z1))
        inner_bot.append((hole_r * ca, hole_r * sa, z0))
        outer_top.append((ro * ca, ro * sa, z1))
        outer_bot.append((ro * ca, ro * sa, z0))
    base = len(mesh.vertices)
    mesh.vertices += inner_top + inner_bot + outer_top + outer_bot
    n = segments
    it, ib, ot, ob = base, base + n, base + 2 * n, base + 3 * n
    for k in range(n):
        j = (k + 1) % n
        # 顶面（+Z）：inner -> outer 逆时针
        mesh.triangles.append((it + k, ot + k, ot + j))
        mesh.triangles.append((it + k, ot + j, it + j))
        # 底面（-Z）
        mesh.triangles.append((ib + k, ob + j, ob + k))
        mesh.triangles.append((ib + k, ib + j, ob + j))
        # 孔壁
        mesh.triangles.append((it + k, ib + k, ib + j))
        mesh.triangles.append((it + k, ib + j, it + j))
        # 外壁
        mesh.triangles.append((ot + k, ot + j, ob + j))
        mesh.triangles.append((ot + k, ob + j, ob + k))


def save_3mf(bits, size_mm, out, *, margin_mm=25.0, hole_mm=3.4, front_tab=True):
    n = bits.shape[0]
    module = size_mm / n
    total = size_mm + 2 * margin_mm
    half = total / 2
    # 图案整体偏移半个模块：让底板中心落在白色模块中央，中孔不破坏图案
    shift = module / 2

    pattern = Mesh()
    for row in range(n):
        for col in range(n):
            if not bits[row, col]:
                continue
            x0 = -size_mm / 2 + col * module + shift
            y0 = -size_mm / 2 + (n - 1 - row) * module + shift
            pattern.add_box(x0, y0, PLATE_MM, x0 + module, y0 + module, PLATE_MM + RELIEF_MM)

    plate = Mesh()
    _plate_with_hole(plate, half, CORNER_R_MM, hole_mm / 2, 0.0, PLATE_MM)
    if front_tab:
        tab_w, tab_len = 26.0, 12.0
        plate.add_prism([(-tab_w / 2, half - 2.0), (tab_w / 2, half - 2.0), (0.0, half + tab_len)],
                        0.0, PLATE_MM)

    model = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
             ' <metadata name="Title">Xelerator ArUco top tag</metadata>',
             ' <metadata name="Designer">RoboCupXelerators</metadata>',
             ' <resources>']
    for oid, (name, mesh) in enumerate((("plate", plate), ("aruco_pattern", pattern)), start=1):
        verts = "".join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in mesh.vertices)
        tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.triangles)
        model.append(f'  <object id="{oid}" type="model" name="{name}">')
        model.append(f'   <mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh>')
        model.append('  </object>')
    model += [' </resources>', ' <build><item objectid="1"/><item objectid="2"/></build>', '</model>']
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "\n".join(model))
    return {"total_mm": total, "module_mm": round(module, 2), "shift_mm": round(shift, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default="4x4_50", choices=sorted(DICTS))
    ap.add_argument("--id", type=int, default=7)
    ap.add_argument("--size-mm", type=float, default=100.0)
    ap.add_argument("--margin-mm", type=float, default=25.0)
    ap.add_argument("--hole-mm", type=float, default=3.4)
    args = ap.parse_args()
    bits = marker_bits(args.dict, args.id)
    n = bits.shape[0]
    # 中孔必须落在白色模块内部，否则会破坏图案：按半模块偏移校验
    module = args.size_mm / n
    row = int((args.size_mm / 2 - module / 2) // module)
    col = row
    if bits[row, col]:
        raise SystemExit(f"id {args.id} 的中心模块是黑色，中孔会破坏图案；换一个 ID 或 --hole-mm 0")
    stem = f"aruco_{args.dict}_id{args.id:02d}"
    save_png(bits, args.size_mm, ROOT / "markers" / f"{stem}_{int(args.size_mm)}mm.png")
    meta = save_3mf(bits, args.size_mm, ROOT / "tag" / f"{stem}_{int(args.size_mm)}mm.3mf",
                    margin_mm=args.margin_mm, hole_mm=args.hole_mm)
    info = {"dictionary": args.dict, "id": args.id, "size_mm": args.size_mm,
            "modules": n, "module_mm": round(args.size_mm / n, 2),
            "plate_mm": PLATE_MM, "relief_mm": RELIEF_MM, "corner_radius_mm": CORNER_R_MM,
            "hole_mm": args.hole_mm, "margin_mm": args.margin_mm, **meta}
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
