"""小尺寸朝向特征（40x40 上限 / 长条形）生成 3MF。

- bar: 120x40 长条，前端 40x40 黑块 + 后端 40x20 黑条（不对称 → 可判前后）
- pad: 44x44 板 + 20x20 黑色角三角（只判角，精度差，实验性）

用法：python tools/make_feature.py --shape bar|pad
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import importlib.util

spec = importlib.util.spec_from_file_location("mk", Path(__file__).with_name("make_tag.py"))
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)

ROOT = Path(__file__).resolve().parents[1]
PLATE = 2.0
RELIEF = 0.6


def build_bar(length: float = 120.0, width: float = 40.0) -> tuple[mk.Mesh, mk.Mesh, dict]:
    plate = mk.Mesh()
    r = 4.0
    # 长条板：圆角用四边形近似（R4 很小，直接直角+倒角即可）
    plate.add_box(-length / 2, -width / 2, 0.0, length / 2, width / 2, PLATE)
    pattern = mk.Mesh()
    front_w = width                      # 40
    front_len = width                    # 40x40 前块
    back_len, back_w = width, width / 2  # 40x20 后条
    pattern.add_box(-length / 2, -width / 2, PLATE,
                    -length / 2 + front_len, width / 2, PLATE + RELIEF)
    pattern.add_box(length / 2 - back_len, -back_w / 2, PLATE,
                    length / 2, back_w / 2, PLATE + RELIEF)
    meta = {"shape": "bar", "length_mm": length, "width_mm": width,
            "front_block_mm": [front_len, front_w], "back_bar_mm": [back_len, back_w],
            "plate_mm": PLATE, "relief_mm": RELIEF,
            "front_hint": "40x40 大方块那一端 = 车头"}
    return plate, pattern, meta


def build_pad(size: float = 40.0, margin: float = 2.0) -> tuple[mk.Mesh, mk.Mesh, dict]:
    plate = mk.Mesh()
    total = size + 2 * margin
    half = total / 2
    mk._plate_with_hole(plate, half, 3.0, 0.0, 0.0, PLATE)
    pattern = mk.Mesh()
    # 前左角 20x20 直角三角形 → 唯一的“方向角”
    x0, y0 = -half, -half
    tri = [(x0, y0), (x0 + 20.0, y0), (x0, y0 + 20.0)]
    pattern.add_prism(tri, PLATE, PLATE + RELIEF)
    meta = {"shape": "pad", "size_mm": size, "margin_mm": margin,
            "corner_triangle_mm": 20.0, "plate_mm": PLATE, "relief_mm": RELIEF,
            "front_hint": "黑色三角所在的角 = 车头左前角"}
    return plate, pattern, meta


def write_3mf(plate: mk.Mesh, pattern: mk.Mesh, out: Path) -> None:
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           ' <metadata name="Title">Xelerator robot heading feature</metadata>',
           ' <resources>']
    for oid, (name, mesh) in enumerate((("plate", plate), ("feature", pattern)), start=1):
        verts = "".join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in mesh.vertices)
        tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.triangles)
        xml.append(f'  <object id="{oid}" type="model" name="{name}">')
        xml.append(f'   <mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh>')
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shape", choices=("bar", "pad"), default="bar")
    args = ap.parse_args()
    if args.shape == "bar":
        plate, pattern, meta = build_bar()
        name = "bar_120x40mm"
    else:
        plate, pattern, meta = build_pad()
        name = "pad_40x40mm"
    out = ROOT / "tag" / f"feature_{name}.3mf"
    write_3mf(plate, pattern, out)
    (ROOT / "tag" / f"feature_{name}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **meta}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
