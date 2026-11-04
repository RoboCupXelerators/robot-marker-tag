"""提手 + 顶标一体件：保持 117.5mm 孔距 / Ø3.3 孔，加宽到 40mm，四周 0.8mm 倒角。

生成 tag/handle_40x129.5mm.3mf：
  - 主体：129.5 x 40 x 6 mm，圆角 R6，两端各一个 Ø3.3 通孔（孔距 117.5）
  - 倒角：顶/底外缘 0.8mm（约 45°，避免割手）
  - 顶面标记：前端 40x40 黑块 + 后端 40x20 黑条（凸起 0.6mm），大方块端=车头
"""

from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENGTH = 129.5
WIDTH = 40.0
THICK = 6.0
HOLE_SPACING = 117.5
HOLE_D = 3.3
CORNER_R = 6.0
BEVEL = 0.8
RELIEF = 0.6
SEGMENTS = 72


class Mesh:
    def __init__(self):
        self.vertices = []
        self.triangles = []

    def add_box(self, x0, y0, z0, x1, y1, z1):
        i = len(self.vertices)
        self.vertices += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                          (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for tri in ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
                    (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
                    (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)):
            self.triangles.append(tuple(i + k for k in tri))


def _inside(x, y, sign, a, b, r):
    """是否在“半个提手”区域内：x 在 sign 一侧，圆角矩形内。"""
    if sign * x < -1e-9:
        return False
    qx = abs(x) - (a - r)
    qy = abs(y) - (b - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) <= r


def _boundary(cx, cy, angle, sign, a, b, r):
    dx, dy = math.cos(angle), math.sin(angle)
    lo, hi = 0.0, 2 * (a + b)
    for _ in range(50):
        t = (lo + hi) / 2
        if _inside(cx + t * dx, cy + t * dy, sign, a, b, r):
            lo = t
        else:
            hi = t
    return lo


def half_handle(cx, sign) -> Mesh:
    """以 (cx,0) 的孔为中心生成半块提手（含孔壁与倒角）。"""
    a, b, r = LENGTH / 2, WIDTH / 2, CORNER_R
    hole_r = HOLE_D / 2
    mesh = Mesh()
    rings = [(0.0, BEVEL), (BEVEL, 0.0), (THICK - BEVEL, 0.0), (THICK, BEVEL)]
    idx = []
    for z, inset in rings:
        ring = []
        for k in range(SEGMENTS):
            ang = 2 * math.pi * k / SEGMENTS
            ro = _boundary(cx, 0.0, ang, sign, a, b, r)
            ca, sa = math.cos(ang), math.sin(ang)
            rr = max(hole_r, ro - inset)
            ring.append((cx + rr * ca, rr * sa, z))
        idx.append(len(mesh.vertices))
        mesh.vertices += ring
    hole_start = len(mesh.vertices)
    for z in (0.0, THICK):
        for k in range(SEGMENTS):
            ang = 2 * math.pi * k / SEGMENTS
            mesh.vertices.append((cx + hole_r * math.cos(ang), hole_r * math.sin(ang), z))
    n = SEGMENTS
    i0, i1, i2, i3 = idx
    h_bot, h_top = hole_start, hole_start + n
    for k in range(n):
        j = (k + 1) % n
        # 底面（z=0，法线 -Z）
        mesh.triangles += [(i0 + k, h_bot + j, h_bot + k), (i0 + k, i0 + j, h_bot + j)]
        # 顶面（z=THICK，法线 +Z）
        mesh.triangles += [(i3 + k, h_top + k, h_top + j), (i3 + k, h_top + j, i3 + j)]
        # 外壁：底倒角、直壁、顶倒角
        mesh.triangles += [(i0 + k, i1 + k, i1 + j), (i0 + k, i1 + j, i0 + j)]
        mesh.triangles += [(i1 + k, i2 + k, i2 + j), (i1 + k, i2 + j, i1 + j)]
        mesh.triangles += [(i2 + k, i3 + k, i3 + j), (i2 + k, i3 + j, i2 + j)]
        # 孔壁
        mesh.triangles += [(h_bot + k, h_top + k, h_top + j), (h_bot + k, h_top + j, h_bot + j)]
    # 切面封口（x=0 处 40x6 截面，四角带 0.8 倒角），另一侧由镜像半块贴合
    cap = [(-(b - BEVEL), 0.0), (b - BEVEL, 0.0), (b, BEVEL), (b, THICK - BEVEL),
           (b - BEVEL, THICK), (-(b - BEVEL), THICK), (-b, THICK - BEVEL), (-b, BEVEL)]
    start = len(mesh.vertices)
    for y, z in cap:
        mesh.vertices.append((0.0, y, z))
    for k in range(1, len(cap) - 1):
        if sign < 0:
            mesh.triangles.append((start, start + k, start + k + 1))
        else:
            mesh.triangles.append((start, start + k + 1, start + k))
    return mesh


def build():
    body = Mesh()
    hole_x = HOLE_SPACING / 2
    for mesh in (half_handle(-hole_x, -1), half_handle(hole_x, +1)):
        base = len(body.vertices)
        body.vertices += mesh.vertices
        body.triangles += [tuple(base + i for i in tri) for tri in mesh.triangles]
    marker = Mesh()
    top_half = WIDTH / 2 - BEVEL          # 顶面比外轮廓内缩 0.8（倒角后）
    # 两块都避开两端 Ø3.3 孔：前 40x36，后 20x36（尺寸不同 → 前大后小，方向唯一）
    marker.add_box(-52.0, -18.0, THICK, -12.0, 18.0, THICK + RELIEF)
    marker.add_box(20.0, -18.0, THICK, 40.0, 18.0, THICK + RELIEF)
    return body, marker


def write_3mf(body, marker, out):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           ' <metadata name="Title">Xelerator handle + heading marker</metadata>',
           ' <resources>']
    for oid, (name, mesh) in enumerate((("handle", body), ("marker", marker)), start=1):
        v = "".join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in mesh.vertices)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.triangles)
        xml.append(f'  <object id="{oid}" type="model" name="{name}">')
        xml.append(f'   <mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh>')
        xml.append('  </object>')
    xml += [' </resources>', ' <build><item objectid="1"/><item objectid="2"/></build>', '</model>']
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "\n".join(xml))


if __name__ == "__main__":
    body, marker = build()
    out = ROOT / "tag" / "handle_129.5x40mm.3mf"
    write_3mf(body, marker, out)
    meta = {"part": "handle+marker", "length_mm": LENGTH, "width_mm": WIDTH, "thick_mm": THICK,
            "hole_spacing_mm": HOLE_SPACING, "hole_d_mm": HOLE_D, "corner_r_mm": CORNER_R,
            "bevel_mm": BEVEL, "relief_mm": RELIEF,
            "marker": {"front_block_mm": [40, 36], "back_block_mm": [20, 36],
                       "front_x_mm": [-52.0, -12.0], "back_x_mm": [20.0, 40.0]},
            "front_hint": "40x36 大方块那一端 = 车头（孔位都在白色区域）"}
    (ROOT / "tag" / "handle_129.5x40mm.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **meta}, ensure_ascii=False))
