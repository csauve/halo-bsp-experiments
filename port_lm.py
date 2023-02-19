from reclaimer.hek.defs.sbsp import sbsp_def
from struct import unpack, pack_into, calcsize
from types import MethodType
from typing import Tuple
from PIL import Image
from dataclasses import dataclass
import argparse

DEBUG_MATCH = False

rendered_vert_format = "<3f 3f 3f 3f 2f"
rendered_vert_size = calcsize(rendered_vert_format)
rendered_vert_unpacker = MethodType(unpack, rendered_vert_format)

@dataclass
class RenderedVert:
    position: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    bitangent: Tuple[float, float, float]
    tangent: Tuple[float, float, float]
    tex_uv: Tuple[float, float]

    def load(buffer, i):
        vert_offset = i * rendered_vert_size
        x,y,z, i,j,k, b0,b1,b2, t0,t1,t2, u,v = rendered_vert_unpacker(buffer[vert_offset: vert_offset + rendered_vert_size])
        return RenderedVert(position=(x, y, z), normal=(i, j, k), bitangent=(b0, b1, b2), tangent=(t0, t1, t2), tex_uv=(u, v))

lm_vert_format = "<3f 2f"
lm_vert_size = calcsize(lm_vert_format)
lm_vert_unpacker = MethodType(unpack, lm_vert_format)
lm_vert_packer = MethodType(pack_into, lm_vert_format)

@dataclass
class LightmapVert:
    incident: Tuple[float, float, float]
    lm_uv: Tuple[float, float]

    def load(buffer, vert_count, i):
        lm_vert_offset = vert_count * rendered_vert_size + i * lm_vert_size
        i,j,k, u,v = lm_vert_unpacker(buffer[lm_vert_offset : lm_vert_offset + lm_vert_size])
        return LightmapVert(incident=(i, j, k), lm_uv=(u, v))
    
    def store(buffer, vert_count, i, lm_vert):
        lm_vert_offset = vert_count * rendered_vert_size + i * lm_vert_size
        lm_vert_packer(buffer, lm_vert_offset, lm_vert.incident[0], lm_vert.incident[1], lm_vert.incident[2], lm_vert.lm_uv[0], lm_vert.lm_uv[1])
    
@dataclass
class IndexedVert:
    rendered: RenderedVert
    lightmap: LightmapVert
    bitmap_index: int
    shader: str

@dataclass
class QueryVert:
    position: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    shader: str
    tex_uv: Tuple[float, float]

def build_kd(verts: list[IndexedVert], axis: int):
    if len(verts) <= 8:
        return (None, verts)
    get_pos_on_axis = lambda v: v.rendered.position[axis]
    verts.sort(key=get_pos_on_axis)
    i_mid = int(len(verts) / 2)
    pos_mid = get_pos_on_axis(verts[i_mid])
    left = build_kd(verts[0 : i_mid], (axis + 1) % 3)
    right = build_kd(verts[i_mid : len(verts)], (axis + 1) % 3)
    return (axis, pos_mid, left, right)

def query_kd(node, q: QueryVert, d: float) -> list[IndexedVert]:
    if node[0] is None:
        return node[1]
    axis, v_mid, left, right = node
    q_axis_pos = q.position[axis]
    results = []
    if q_axis_pos - d <= v_mid:
        results += query_kd(left, q, d)
    if q_axis_pos + d >= v_mid:
        results += query_kd(right, q, d)
    return results


def sqdst3d(a, b):
    a0, a1, a2 = a
    b0, b1, b2 = b
    return (a0 - b0) * (a0 - b0) + (a1 - b1) * (a1 - b1) + (a2 - b2) * (a2 - b2)

def dot3d(a, b):
    a0, a1, a2 = a
    b0, b1, b2 = b
    return (a0 * b0) + (a1 * b1) + (a2 * b2)

def sqdst2d(a, b):
    if a is None or b is None:
        return 0
    a0, a1 = a
    b0, b1 = b
    return (a0 - b0) * (a0 - b0) + (a1 - b1) * (a1 - b1)

def find_match(src_kd, q: QueryVert, d: float, orig_bitmap_index: int, prev_matched_bitmap_index: int, prev_matched_lm_uv) -> IndexedVert:
    candidates = query_kd(src_kd, q, d)

    shader_pred = lambda c: c.shader == q.shader
    dist_pred = lambda c: sqdst3d(q.position, c.rendered.position) <= d * d
    normal_pred = lambda c: sqdst3d(q.normal, c.rendered.normal) < 0.001
    tex_uv_pred = lambda c: sqdst2d(q.tex_uv, c.rendered.tex_uv) < 0.001
    rate = lambda c: sqdst2d(prev_matched_lm_uv, c.lightmap.lm_uv)

    candidates = list(filter(
        lambda c:
            shader_pred(c) and
            dist_pred(c) and
            normal_pred(c) and
            tex_uv_pred(c),
        candidates
    ))
    if len(candidates) == 0:
        raise Exception("No candidates found for a vert. Increase d")
    
    candidates.sort(key=rate)
    best_match: IndexedVert = candidates[0]
    
    if DEBUG_MATCH and orig_bitmap_index != best_match.bitmap_index:
        print(f"\nquery: {q} {orig_bitmap_index} {prev_matched_bitmap_index}")
        for c in candidates:
            print(f"\ncandidate: {c}")
        raise Exception("Bitmap index mismatch")
    return best_match

def load_src_verts(bsp_path):
    bsp_tag = sbsp_def.build(filepath=bsp_path)
    bsp = bsp_tag.data.tagdata
    all_verts = []

    for lightmap in bsp.lightmaps.STEPTREE:
        # skip add-blended shaders like lights; they have no lightmaps
        if lightmap.bitmap_index == -1:
            continue
        for material in lightmap.materials.STEPTREE:
            vert_count = material.vertices_count # rendered verts count
            lm_vert_count = material.lightmap_vertices_count # lm verts count
            assert vert_count == lm_vert_count
            vert_buffer = material.uncompressed_vertices.STEPTREE
            for i in range(vert_count):
                all_verts.append(IndexedVert(
                    rendered=RenderedVert.load(vert_buffer, i),
                    lightmap=LightmapVert.load(vert_buffer, vert_count, i),
                    bitmap_index=lightmap.bitmap_index,
                    shader=material.shader.filepath,
                ))
    return build_kd(all_verts, 0)

def port_lm(src_bsp_path, dst_bsp_path, d, uv_transforms):
    print("Porting lightmap UVs")
    src_kd = load_src_verts(src_bsp_path)
    dst_bsp_tag = sbsp_def.build(filepath=dst_bsp_path)
    dst_bsp = dst_bsp_tag.data.tagdata

    for i_lightmap, lightmap in enumerate(dst_bsp.lightmaps.STEPTREE):
        if lightmap.bitmap_index == -1:
            continue
        print(f"Reassigning lightmap {i_lightmap} bitmap index to 0")
        orig_bitmap_index = lightmap.bitmap_index
        if not DEBUG_MATCH:
            lightmap.bitmap_index = 0
        for i_material, material in enumerate(lightmap.materials.STEPTREE):
            vert_count = material.vertices_count  # rendered verts count
            lm_vert_count = material.lightmap_vertices_count # lm verts count
            assert vert_count == lm_vert_count
            vert_buffer = material.uncompressed_vertices.STEPTREE  # rendered verts buffer

            prev_matched_bitmap_index = None
            prev_matched_lm_uv = None

            print(f"Updating {vert_count} lightmap UVs for material {i_material}")
            for i in range(vert_count):
                rendered_vert = RenderedVert.load(vert_buffer, i)
                query_vert = QueryVert(
                    position=rendered_vert.position,
                    normal=rendered_vert.normal,
                    shader=material.shader.filepath,
                    tex_uv=rendered_vert.tex_uv
                )

                match = find_match(src_kd, query_vert, d, orig_bitmap_index, prev_matched_bitmap_index, prev_matched_lm_uv)
                prev_matched_bitmap_index = match.bitmap_index
                prev_matched_lm_uv = match.lightmap.lm_uv
                transformed_uv = uv_transforms[match.bitmap_index](match.lightmap.lm_uv)

                LightmapVert.store(vert_buffer, vert_count, i, LightmapVert(
                    incident=match.lightmap.incident,
                    lm_uv=transformed_uv
                ))

    print(f"Writing BSP tag to {dst_bsp_path}")
    dst_bsp_tag.serialize(backup=False, temp=False)

def is_gap(img, x, y):
    r, g, b, a = img.getpixel((x, y))
    return (r == 0 and g == 0 and b == 255) or a == 0

def is_vacant(dst_pages, x, y):
    for dst_page in dst_pages:
        dst_min_x, dst_min_y = dst_page[0]
        dst_max_x, dst_max_y = dst_page[1]
        if x >= dst_min_x and x < dst_max_x and y >= dst_min_y and y < dst_max_y:
            return False
    return True

def is_vacant_rect(dst_pages, x_min, y_min, w, h):
    for ty in range(y_min, y_min + h):
        for tx in range(x_min, x_min + w):
            if not is_vacant(dst_pages, tx, ty):
                return False
    return True

def find_vacancy(dst_pages, dst_w, dst_h, page_w, page_h):
    for dst_min_y in range(0, dst_h - page_h):
        for dst_min_x in range(0, dst_w - page_w):
            if is_vacant_rect(dst_pages, dst_min_x, dst_min_y, page_w, page_h):
                return [(dst_min_x, dst_min_y), (dst_min_x + page_w, dst_min_y + page_h)]
    return None

def flatten_lm_bitmap(src_tif_path, dst_tif_path, dst_w, dst_h):
    dst_img = Image.new("RGBA", (dst_w, dst_h))

    src_img = Image.open(src_tif_path)
    src_w = src_img.size[0]
    src_h = src_img.size[1]
    print(f"Lightmap source plate is {src_w}x{src_h}")
    src_pages = []
    
    # find pages
    border = 1
    in_gap = True
    bitmap_index = 0
    for y in range(border, src_h):
        found_gap_y = is_gap(src_img, border, y)
        if in_gap and not found_gap_y:
            src_pages.append([(border, y), None, bitmap_index])
            in_gap = False
            bitmap_index += 1
        elif not in_gap and found_gap_y:
            for x in range(border, src_w):
                if is_gap(src_img, x, y - 1):
                    src_pages[-1][1] = (x, y)
                    break
                assert x != src_w - 1
            in_gap = True
    print(f"Found {len(src_pages)} pages")

    # pack pages into destination texture
    total_page_area = 0
    dst_area = dst_w * dst_h
    src_pages.sort(reverse=True, key=lambda pg: (pg[1][0] - pg[0][0]) * (pg[1][1] - pg[0][1]))
    dst_pages = []
    for src_page in src_pages:
        src_min_x, src_min_y = src_page[0]
        src_max_x, src_max_y = src_page[1]
        page_w = src_max_x - src_min_x
        page_h = src_max_y - src_min_y
        vacancy = find_vacancy(dst_pages, dst_w, dst_h, page_w, page_h)
        if vacancy is None:
            raise Exception("Couldn't pack all pages. Increase dimensions")
        total_page_area += page_w * page_h
        dst_pages.append(vacancy)
    print(f"Packed pages, with utilization: {total_page_area / dst_area}")

    # copy to dst and build UV transforms
    print("Copying pages and creating UV transforms")
    uv_transforms = [None] * len(src_pages)
    for src_page, dst_page in [*zip(src_pages, dst_pages)]:
        src_min_x, src_min_y = src_page[0]
        src_max_x, src_max_y = src_page[1]
        bitmap_index = src_page[2]
        dst_min_x, dst_min_y = dst_page[0]
        dst_max_x, dst_max_y = dst_page[1]
        page_w = src_max_x - src_min_x
        page_h = src_max_y - src_min_y
        
        # left upper right lower
        src_box = (src_min_x, src_min_y, src_max_x, src_max_y)
        dst_box = (dst_min_x, dst_min_y, dst_max_x, dst_max_y)
        print(f"{src_page} to {dst_page}")
        region = src_img.crop(src_box)
        dst_img.paste(region, dst_box)

        uv_transform = (
            lambda page_w,dst_min_x,dst_w,page_h,dst_min_y,dst_h: lambda uv: ((uv[0] * page_w + dst_min_x) / dst_w, (uv[1] * page_h + dst_min_y) / dst_h)
        )(page_w,dst_min_x,dst_w,page_h,dst_min_y,dst_h)
        uv_transforms[bitmap_index] = uv_transform
    
    dst_img.save(dst_tif_path)
    return uv_transforms

parser = argparse.ArgumentParser()
parser.add_argument("src", help="Path to the donor BSP tag")
parser.add_argument("dst", help="Path to the receiver BSP tag")
parser.add_argument("d", type=float, help="Search distance")
parser.add_argument("src_tif", help="Path to the lightmap tiff source plate")
parser.add_argument("dst_tif", help="Path to write the flattened lightmap")
parser.add_argument("dst_w", type=int, help="Width of flattened lightmap")
parser.add_argument("dst_h", type=int, help="Width of flattened lightmap")
args = parser.parse_args()

uv_transforms = flatten_lm_bitmap(args.src_tif, args.dst_tif, args.dst_w, args.dst_h)
port_lm(args.src, args.dst, args.d, uv_transforms)

