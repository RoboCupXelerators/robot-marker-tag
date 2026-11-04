"""提手兼标记：129.5x14x6 圆角条 + 前端凸起圆钮（= 车头标记），孔距 117.5 / Ø3.3。

条状长轴给朝向（长基线），前端圆钮给方向（大色块），一件两用。
"""

from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENGTH, WIDTH, THICK = 129.5, 14.0, 6.0
HOLE_SPACING, HOLE_D = 117.5, 3.3
CORNER_R, BEVEL = 7.0, 0.8
KNOB_D, KNOB_H, KNOB_X = 22.0, 5.0, -44.0
SEG = 72


class Mesh:
    def __init__(self):
        self.vertices = []
        self.triangles = []

    def add_prism(self, poly, z0, z1):
        n = len(poly)
        b = len(self.vertices)
        for z in (z0, z1):
            self.vertices += [(x, y, z) for x, y in poly]
        cx = sum(p[0] for p in poly) / n; cy = sum(p[1] for p in poly) / n
        cb = len(self.vertices); self.vertices.append((cx, cy, z0))
        ct = len(self.vertices); self.vertices.append((cx, cy, z1))
        for i in range(n):
            j = (i + 1) % n
            self.triangles += [(cb, b + j, b + i), (ct, b + n + i, b + n + j),
                               (b + i, b + j, b + n + j), (b + i, b + n + j, b + n + i)]


def _inside(x, y, sign, a, b, r):
    if sign * x < -1e-9:
        return False
    qx = abs(x) - (a - r); qy = abs(y) - (b - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) <= r


def _boundary(cx, sign, ang, a, b, r):
    lo, hi = 0.0, 2 * (a + b)
    dx, dy = math.cos(ang), math.sin(ang)
    for _ in range(50):
        t = (lo + hi) / 2
        if _inside(cx + t * dx, t * dy, sign, a, b, r):
            lo = t
        else:
            hi = t
    return lo


def half(hole_x, sign):
    mesh = Mesh()
    a, b, r = LENGTH / 2, WIDTH / 2, CORNER_R
    hole_r = HOLE_D / 2
    rings = [(0.0, BEVEL), (BEVEL, 0.0), (THICK - BEVEL, 0.0), (THICK, BEVEL)]
    idx = []
    for z, inset in rings:
        start = len(mesh.vertices)
        for k in range(SEG):
            ang = 2 * math.pi * k / SEG
            ro = _boundary(hole_x, sign, ang, a, b, r)
            rr = max(hole_r, ro - inset)
            mesh.vertices.append((hole_x + rr * math.cos(ang), rr * math.sin(ang), z))
        idx.append(start)
    hb = len(mesh.vertices)
    for z in (0.0, THICK):
        for k in range(SEG):
            ang = 2 * math.pi * k / SEG
            mesh.vertices.append((hole_x + hole_r * math.cos(ang), hole_r * math.sin(ang), z))
    ht = hb + SEG
    i0, i1, i2, i3 = idx
    for k in range(SEG):
        j = (k + 1) % SEG
        mesh.triangles += [(i0 + k, hb + j, hb + k), (i0 + k, i0 + j, hb + j),
                           (i3 + k, ht + k, ht + j), (i3 + k, ht + j, i3 + j),
                           (i0 + k, i1 + k, i1 + j), (i0 + k, i1 + j, i0 + j),
                           (i1 + k, i2 + k, i2 + j), (i1 + k, i2 + j, i1 + j),
                           (i2 + k, i3 + k, i3 + j), (i2 + k, i3 + j, i2 + j),
                           (hb + k, ht + k, ht + j), (hb + k, ht + j, hb + j)]
    gw = b - BEVEL
    cap = [(-(gw - BEVEL), 0.0), (gw - BEVEL, 0.0), (gw, BEVEL), (gw, THICK - BEVEL),
           (gw - BEVEL, THICK), (-(gw - BEVEL), THICK), (-gw, THICK - BEVEL), (-gw, BEVEL)]
    s = len(mesh.vertices)
    mesh.vertices += [(0.0, y, z) for y, z in cap]
    for k in range(1, len(cap) - 1):
        mesh.triangles.append((s, s + k, s + k + 1) if sign < 0 else (s, s + k + 1, s + k))
    return mesh


def build():
    body = Mesh()
    for m in (half(-HOLE_SPACING / 2, -1), half(HOLE_SPACING / 2, +1)):
        off = len(body.vertices)
        body.vertices += m.vertices
        body.triangles += [tuple(off + i for i in t) for t in m.triangles]
    knob = Mesh()
    poly = [(KNOB_X + KNOB_D / 2 * math.cos(2 * math.pi * k / 24),
             KNOB_D / 2 * math.sin(2 * math.pi * k / 24)) for k in range(24)]
    knob.add_prism(poly, THICK - 0.2, THICK + KNOB_H)
    return body, knob


def write(out, body, knob):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           ' <resources>']
    for oid, (name, mesh) in enumerate((("handle", body), ("front_knob", knob)), start=1):
        v = "".join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in mesh.vertices)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.triangles)
        xml.append(f'  <object id="{oid}" type="model" name="{name}">'
                   f'<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>')
    xml += [' </resources>', ' <build><item objectid="1"/><item objectid="2"/></build>', '</model>']
    types = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "\n".join(xml))


if __name__ == "__main__":
    body, knob = build()
    out = ROOT / "tag" / "handle_rod_129.5x14mm.3mf"
    write(out, body, knob)
    meta = {"part": "handle+marker", "length_mm": LENGTH, "width_mm": WIDTH, "thick_mm": THICK,
            "hole_spacing_mm": HOLE_SPACING, "hole_d_mm": HOLE_D, "corner_r_mm": CORNER_R,
            "bevel_mm": BEVEL, "knob_d_mm": KNOB_D, "knob_h_mm": KNOB_H, "knob_x_mm": KNOB_X,
            "front_hint": "圆钮那一端 = 车头；长轴给朝向，圆钮给方向"}
    (ROOT / "tag" / "handle_rod_129.5x14mm.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **meta}, ensure_ascii=False))
