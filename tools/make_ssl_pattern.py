"""SSL 风格点阵板：装在雷达顶部，用 4 个点解算位置+朝向（≤2°）。

布局（+x = 车头）：
  大三角 3 点（边长 --triangle，点径 --dot-d）+ 1 个偏置小点（点径 0.62×）
  缺角 + 小点位置共同确定朝向，不存在 180° 歧义。

用法：python tools/make_ssl_pattern.py --diameter 90 --triangle 60
"""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Mesh:
    def __init__(self):
        self.vertices = []
        self.triangles = []

    def add_prism(self, polygon, z0, z1):
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
            self.triangles.append((cb, base + j, base + i))
            self.triangles.append((ct, base + n + i, base + n + j))
            self.triangles += [(base + i, base + j, base + n + j),
                               (base + i, base + n + j, base + n + i)]


def circle(cx, cy, r, n=24):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def annulus(outer_r, inner_r, z0, z1, n=96):
    mesh = Mesh()
    for k in range(n):
        ang = 2 * math.pi * k / n
        ca, sa = math.cos(ang), math.sin(ang)
        mesh.vertices += [(outer_r * ca, outer_r * sa, z0), (inner_r * ca, inner_r * sa, z0),
                          (outer_r * ca, outer_r * sa, z1), (inner_r * ca, inner_r * sa, z1)]
    for k in range(n):
        j = (k + 1) % n
        o0, i0, o1, i1 = 4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3
        oj, ij = 4 * j, 4 * j + 1
        mesh.triangles += [(o0, oj, ij), (o0, ij, i0)]               # 底
        mesh.triangles += [(o1, i1, ij + 2), (o1, ij + 2, oj + 2)]   # 顶
        mesh.triangles += [(o0, o1, oj + 2), (o0, oj + 2, oj)]       # 外壁
        mesh.triangles += [(i0, ij, ij + 3), (i0, ij + 3, i1)]       # 内壁
    return mesh


def build(diameter=90.0, triangle=60.0, dot_d=12.0, thickness=3.0, hole=3.4, relief=0.6):
    R = diameter / 2
    plate = annulus(R, hole / 2, 0.0, thickness)
    # 外缘 0.8 倒角
    bevel = annulus(R, hole / 2, thickness - 0.8, thickness)
    for i in range(0, len(bevel.vertices), 4):
        for k in (0, 2):  # 只把外圈收缩
            x, y, z = bevel.vertices[i + k]
            f = (R - 0.8) / R
            bevel.vertices[i + k] = (x * f, y * f, z)
    offset = len(plate.vertices)
    plate.vertices += bevel.vertices
    plate.triangles += [tuple(offset + i for i in t) for t in bevel.triangles]

    # 长基线三角形：底边在后（-x），顶点在前（+x），基线尽量拉长以压低朝向噪声
    back_x = -(R - dot_d / 2 - 3.0)
    half_w = min(R * 0.42, triangle / 2)
    apex_x = R - dot_d / 2 - 3.0
    dots = [(back_x, -half_w, dot_d), (back_x, half_w, dot_d), (apex_x, 0.0, dot_d),
            (apex_x - 28.0, -half_w * 0.55, dot_d * 0.58)]
    pattern = Mesh()
    for x, y, d in dots:
        pattern.add_prism(circle(x, y, d / 2, 20), thickness, thickness + relief)
    return plate, pattern, dots


def write_3mf(plate, pattern, out, meta):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           f' <metadata name="Title">SSL-style pattern plate {meta["diameter_mm"]}mm</metadata>',
           ' <resources>']
    for oid, (name, mesh) in enumerate((("plate", plate), ("dots", pattern)), start=1):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diameter", type=float, default=90.0)
    ap.add_argument("--triangle", type=float, default=60.0)
    ap.add_argument("--dot-d", type=float, default=12.0)
    ap.add_argument("--thickness", type=float, default=3.0)
    ap.add_argument("--hole", type=float, default=3.4)
    args = ap.parse_args()
    plate, pattern, dots = build(args.diameter, args.triangle, args.dot_d, args.thickness, args.hole)
    name = f"ssl_pattern_d{int(args.diameter)}_t{int(args.triangle)}"
    out = ROOT / "tag" / f"{name}.3mf"
    write_3mf(plate, pattern, out, {"diameter_mm": args.diameter})
    base = math.hypot(dots[2][0] - dots[0][0], dots[2][1] - dots[0][1])
    px_per_mm = 3.25 / 10.0
    err_deg = math.degrees(math.atan2(0.5, base * px_per_mm / 2.0))
    meta = {"diameter_mm": args.diameter, "triangle_mm": args.triangle, "dot_d_mm": args.dot_d,
            "baseline_mm": round(base, 1), "est_heading_err_deg": round(err_deg, 1),
            "small_dot_d_mm": round(args.dot_d * 0.62, 1), "thickness_mm": args.thickness,
            "center_hole_mm": args.hole, "relief_mm": 0.6,
            "dots": [[round(x, 1), round(y, 1), round(d, 1)] for x, y, d in dots],
            "front_hint": "单个大点（三角形顶点）那一侧 = 车头；小点在前方偏右"}
    (ROOT / "tag" / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **meta}, ensure_ascii=False))


if __name__ == "__main__":
    main()
