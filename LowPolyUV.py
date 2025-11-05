bl_info = {
    "name": "LowPolyUV",
    "author": "Rainer Wahnsinn",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "UV Editor > UVs > Scale & Snap Palette",
    "description": "Scale UV islands and snap face colors to a clustered palette",
    "category": "UV",
}

import bpy
import bmesh
from mathutils import Vector
import math
from collections import defaultdict

def scale_faces_to_center(scale_factor=0.1):
    """
    For each selected face:
    1. Compute its UV center.
    2. Scale all its UVs toward that center.
    3. Optionally collapse all UVs to the center (for palette snapping).
    """
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("Please select a mesh object")
        return

    prev_mode = obj.mode
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        print("No UV layer found")
        bpy.ops.object.mode_set(mode=prev_mode)
        return

    selected_faces = [f for f in bm.faces if f.select]
    if not selected_faces:
        print("No faces selected")
        bpy.ops.object.mode_set(mode=prev_mode)
        return

    for face in selected_faces:
        # Compute UV center for the face
        uvs = [l[uv_layer].uv for l in face.loops]
        center = sum((uv.copy() for uv in uvs), Vector((0, 0))) / len(uvs)

        # Shrink UVs toward center
        for uv in uvs:
            uv -= center
            uv *= scale_factor
            uv += center

        # Collapse all UVs to center (optional, ensures one UV per face)
        for l in face.loops:
            l[uv_layer].uv = center.copy()

    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode=prev_mode)
    print(f"✅ Scaled and collapsed {len(selected_faces)} faces individually toward their centers")

# ------------------------------
# K-means clustering for colors
# ------------------------------
def kmeans_colors_balanced(colors, k, max_iters=20, merge_threshold=0.02):
    """
    Balanced K-means for colors:
    - Preserves rare light colors.
    - Reduces redundant dark clusters.
    - colors: list of [r,g,b,a]
    """
    import random
    import math

    if len(colors) <= k:
        return colors.copy()

    # Initialize clusters with diverse colors (farthest-point sampling)
    clusters = [random.choice(colors)]
    while len(clusters) < k:
        def min_dist(c):
            return min(sum((c[i]-cl[i])**2 for i in range(4)) for cl in clusters)
        clusters.append(max(colors, key=min_dist))

    for _ in range(max_iters):
        assignments = [[] for _ in range(k)]
        for c in colors:
            # Weight by luminance to favor rare light colors
            lum = 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]
            weight = 1.0 / (lum + 0.01)
            best_idx = min(range(k), key=lambda i: sum((c[j]-clusters[i][j])**2 for j in range(4)) / weight)
            assignments[best_idx].append(c)
        for i in range(k):
            if assignments[i]:
                clusters[i] = [sum(col[j] for col in assignments[i])/len(assignments[i]) for j in range(4)]

    # Merge clusters that are very close
    merged = []
    for c in clusters:
        if not merged:
            merged.append(c)
            continue
        if min(math.sqrt(sum((c[i]-m[i])**2 for i in range(4))) for m in merged) > merge_threshold:
            merged.append(c)
    return merged


# ------------------------------
# Sample face colors function
# ------------------------------
def sample_face_colors_safe_multimat(obj, max_colors=16, downscale_max=512, use_downscale=True):
    """Sample face colors safely for all selected faces, respecting multiple materials."""
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        print("No UV layer found")
        return [], None

    face_colors = []

    # Cache downscaled images per material to avoid resampling repeatedly
    material_images = {}

    for face in bm.faces:
        if not face.select:
            continue

        mat_idx = face.material_index
        if mat_idx >= len(obj.material_slots):
            continue
        mat = obj.material_slots[mat_idx].material
        if not mat or not mat.node_tree:
            continue

        # Find image texture node
        image = None
        if mat.name in material_images:
            image = material_images[mat.name]
        else:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    image = node.image
                    break
            if image:
                # Optional downscale
                if use_downscale:
                    width, height = image.size
                    scale = min(1.0, downscale_max / max(width, height))
                    if scale < 1.0:
                        tmp = bpy.data.images.new(
                            name=f"{image.name}_scaled_tmp",
                            width=width, height=height, alpha=True
                        )
                        tmp.pixels.foreach_set(image.pixels[:])
                        tmp.scale(max(1, int(width*scale)), max(1, int(height*scale)))
                        image_to_use = tmp
                    else:
                        image_to_use = image
                else:
                    image_to_use = image
                material_images[mat.name] = image_to_use
            else:
                continue  # skip face if no texture

        w, h = image_to_use.size
        pixels = list(image_to_use.pixels)

        # Sample UV center
        uvs = [l[uv_layer].uv.copy() for l in face.loops]
        center = sum(uvs, Vector((0, 0))) / len(uvs)
        center.x = max(0.0, min(1.0, center.x))
        center.y = max(0.0, min(1.0, center.y))

        px = int(center.x * (w - 1))
        py = int(center.y * (h - 1))
        idx = (py * w + px) * 4
        idx = max(0, min(idx, len(pixels) - 4))
        color = pixels[idx:idx + 4]

        # Fallback averaging if very dark or transparent
        if sum(color[:3]) < 0.01 or color[3] < 0.01:
            r, g, b, a = 0, 0, 0, 0
            count = 0
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    nx = max(0, min(px + dx, w - 1))
                    ny = max(0, min(py + dy, h - 1))
                    nidx = (ny * w + nx) * 4
                    c = pixels[nidx:nidx + 4]
                    r += c[0]; g += c[1]; b += c[2]; a += c[3]
                    count += 1
            color = [r/count, g/count, b/count, a/count]

        face_colors.append(color)

    if not face_colors:
        print("No face colors found.")
        return [], None

    clustered_colors = kmeans_colors_balanced(face_colors, max_colors)
    return clustered_colors, None  # scaled images are per-material now, can remove later

# ------------------------------
# Create palette function
# ------------------------------
def create_square_palette(colors, name="PaletteTexture", block_size=8):
    n = len(colors)
    grid_size = math.ceil(math.sqrt(n))
    img_size = grid_size * block_size
    img = bpy.data.images.new(name, width=img_size, height=img_size)
    pixels = [0.0] * (img_size * img_size * 4)

    for idx, color in enumerate(colors):
        row = idx // grid_size
        col = idx % grid_size
        for x in range(col*block_size, (col+1)*block_size):
            for y in range(row*block_size, (row+1)*block_size):
                pix_idx = (y * img_size + x) * 4
                pixels[pix_idx:pix_idx+4] = color
    img.pixels = pixels
    img.pack()
    return img, grid_size


# ------------------------------
# Palette cache
# ------------------------------
class PaletteCache:
    def __init__(self, colors, grid_size):
        self.colors = colors
        self.grid_size = grid_size
        self.positions = []
        for idx, color in enumerate(colors):
            row = idx // grid_size
            col = idx % grid_size
            u = (col + 0.5) / grid_size
            v = (row + 0.5) / grid_size
            self.positions.append(Vector((u, v)))

    def closest_color_index(self, color):
        min_dist = float('inf')
        best_idx = 0
        for i, c in enumerate(self.colors):
            dist = sum((color[j] - c[j])**2 for j in range(4))
            if dist < min_dist:
                min_dist = dist
                best_idx = i
        return best_idx


def snap_faces_to_palette(obj, max_colors=16, block_size=8, use_downscale=True, downscale_max=512):
    """
    Snap selected faces to a clustered palette.
    Fast path for single material + single texture.
    Supports multi-material too.
    """
    if obj.type != 'MESH':
        print("Select a mesh object!")
        return

    prev_mode = obj.mode
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        print("No UV layer found")
        bpy.ops.object.mode_set(mode=prev_mode)
        return

    # --------------------------
    # Detect single-material fast path
    # --------------------------
    if len(obj.material_slots) == 1:
        mat = obj.material_slots[0].material
        image = None
        if mat and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    image = node.image
                    break
        if image:
            # Single material + texture path
            width, height = image.size
            scale = 1.0
            if use_downscale and max(width, height) > downscale_max:
                scale = downscale_max / max(width, height)
                tmp_img = bpy.data.images.new(
                    name=f"{image.name}_tmp",
                    width=width, height=height, alpha=True
                )
                tmp_img.pixels.foreach_set(image.pixels[:])
                tmp_img.scale(max(1, int(width*scale)), max(1, int(height*scale)))
                image = tmp_img
                width, height = image.size

            pixels = list(image.pixels)
            face_colors = []
            face_map = {}

            for face in bm.faces:
                if not face.select:
                    continue
                uvs = [l[uv_layer].uv.copy() for l in face.loops]
                center = sum(uvs, Vector((0,0))) / len(uvs)
                center.x = max(0.0, min(1.0, center.x))
                center.y = max(0.0, min(1.0, center.y))

                px = int(center.x * (width-1))
                py = int(center.y * (height-1))
                idx = (py * width + px) * 4
                idx = max(0, min(idx, len(pixels)-4))
                color = pixels[idx:idx+4]

                # Fallback averaging if very dark or transparent
                if sum(color[:3]) < 0.01 or color[3] < 0.01:
                    r=g=b=a=0
                    count=0
                    for dx in (-1,0,1):
                        for dy in (-1,0,1):
                            nx = max(0, min(px+dx, width-1))
                            ny = max(0, min(py+dy, height-1))
                            nidx = (ny * width + nx) * 4
                            c = pixels[nidx:nidx+4]
                            r+=c[0]; g+=c[1]; b+=c[2]; a+=c[3]; count+=1
                    color=[r/count, g/count, b/count, a/count]

                face_colors.append(color)
                face_map[face] = color

            clustered_colors = kmeans_colors_balanced(face_colors, max_colors)
            palette_img, grid_size = create_square_palette(clustered_colors, name="PaletteTexture", block_size=block_size)
            palette_cache = PaletteCache(clustered_colors, grid_size)

            # Snap UVs
            for face, color in face_map.items():
                idx = palette_cache.closest_color_index(color)
                target_uv = palette_cache.positions[idx]
                for l in face.loops:
                    l[uv_layer].uv = target_uv.copy()

            bmesh.update_edit_mesh(obj.data)
            bpy.ops.object.mode_set(mode=prev_mode)
            obj.data.update()
            print("✅ Faces snapped (single-material fast path).")
            return

def snap_faces_to_palette_multimat(
    obj, max_colors=16, block_size=8, use_downscale=True, downscale_max=512
):
    """Snap selected faces to a clustered palette, respecting multiple materials."""
    if obj.type != 'MESH':
        print("Select a mesh object!")
        return

    prev_mode = obj.mode
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        print("No UV layer found")
        bpy.ops.object.mode_set(mode=prev_mode)
        return

    # Sample face colors (multi-material safe)
    face_colors, _ = sample_face_colors_safe_multimat(
        obj, max_colors=max_colors, downscale_max=downscale_max, use_downscale=use_downscale
    )
    if not face_colors:
        print("No face colors found or textures missing.")
        bpy.ops.object.mode_set(mode=prev_mode)
        return

    # Create clustered palette
    palette_img, grid_size = create_square_palette(face_colors, block_size=block_size)
    palette_cache = PaletteCache(face_colors, grid_size)

    # Prepare material-to-image mapping (downscaled if requested)
    material_images = {}
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.node_tree:
            continue
        image = None
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                image = node.image
                break
        if not image:
            continue
        # Downscale
        if use_downscale:
            width, height = image.size
            scale = min(1.0, downscale_max / max(width, height))
            if scale < 1.0:
                tmp = bpy.data.images.new(
                    name=f"{image.name}_scaled_tmp",
                    width=width, height=height,
                    alpha=True
                )
                tmp.pixels.foreach_set(image.pixels[:])
                tmp.scale(max(1, int(width*scale)), max(1, int(height*scale)))
                material_images[mat.name] = tmp
            else:
                material_images[mat.name] = image
        else:
            material_images[mat.name] = image

    # Snap faces
    for face in bm.faces:
        if not face.select:
            continue

        mat_idx = face.material_index
        if mat_idx >= len(obj.material_slots):
            continue
        mat = obj.material_slots[mat_idx].material
        if not mat or mat.name not in material_images:
            continue

        image = material_images[mat.name]
        pixels = list(image.pixels)
        w, h = image.size

        # Sample UV center
        uvs = [l[uv_layer].uv.copy() for l in face.loops]
        center = sum(uvs, Vector((0, 0))) / len(uvs)
        center.x = max(0.0, min(1.0, center.x))
        center.y = max(0.0, min(1.0, center.y))

        px = int(center.x * (w - 1))
        py = int(center.y * (h - 1))
        idx = (py * w + px) * 4
        idx = max(0, min(idx, len(pixels)-4))
        face_color = pixels[idx:idx+4]

        # Fallback averaging for very dark/transparent pixels
        if sum(face_color[:3]) < 0.01 or face_color[3] < 0.01:
            r, g, b, a = 0, 0, 0, 0
            count = 0
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    nx = max(0, min(px+dx, w-1))
                    ny = max(0, min(py+dy, h-1))
                    nidx = (ny * w + nx) * 4
                    c = pixels[nidx:nidx+4]
                    r += c[0]; g += c[1]; b += c[2]; a += c[3]
                    count += 1
            face_color = [r/count, g/count, b/count, a/count]

        # Snap to palette
        palette_idx = palette_cache.closest_color_index(face_color)
        target_uv = palette_cache.positions[palette_idx]

        for l in face.loops:
            l[uv_layer].uv = target_uv.copy()

    # Cleanup
    for img in material_images.values():
        if img.name.endswith("_scaled_tmp"):
            bpy.data.images.remove(img, do_unlink=True)

    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode=prev_mode)
    obj.data.update()
    print(f"✅ Faces snapped to clustered palette (multi-material safe).")

# ------------------------------
# Blender Operator
# ------------------------------
class UV_OT_ScaleAndSnapPalette(bpy.types.Operator):
    bl_idname = "uv.scale_and_snap_palette"
    bl_label = "LowPolyUV"
    bl_options = {'REGISTER', 'UNDO'}

    scale_factor: bpy.props.FloatProperty(
        name="UV Island Scale",
        default=0.1,
        min=0.0,
        max=1.0,
        description="Scale each UV island before snapping"
    )

    max_colors: bpy.props.IntProperty(
        name="Max Colors",
        default=16,
        min=1,
        description="Maximum number of colors in palette"
    )

    block_size: bpy.props.IntProperty(
        name="Block Size",
        default=8,
        min=1,
        description="Size of each color block in pixels"
    )

    use_downscale: bpy.props.BoolProperty(
        name="Use Downscaled Image",
        default=True,
        description="Use a scaled-down copy of the texture for faster color sampling"
    )

    downscale_max: bpy.props.IntProperty(
        name="Downscale Max Size",
        default=512,
        min=64,
        max=4096,
        description="Maximum resolution (in pixels) for downscaled image"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "scale_factor")
        layout.prop(self, "max_colors")
        layout.prop(self, "block_size")
        layout.prop(self, "use_downscale")
        if self.use_downscale:
            layout.prop(self, "downscale_max")

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object!")
            return {'CANCELLED'}

        # 1️⃣ Scale UVs toward center
        scale_faces_to_center(self.scale_factor)

        # 2️⃣ Smart snapping to clustered palette (fast path if single material)
        snap_faces_to_palette(
            obj,
            max_colors=self.max_colors,
            block_size=self.block_size,
            use_downscale=self.use_downscale,
            downscale_max=self.downscale_max
        )

        self.report(
            {'INFO'},
            f"✅ UVs scaled and snapped ({'single-material fast path' if len(obj.material_slots)==1 else 'multi-material'})"
        )
        return {'FINISHED'}

# ------------------------------
# Menu integration
# ------------------------------
def menu_func(self, context):
    self.layout.operator(UV_OT_ScaleAndSnapPalette.bl_idname, icon='COLOR')


# ------------------------------
# Registration
# ------------------------------
classes = [UV_OT_ScaleAndSnapPalette]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if hasattr(bpy.types, "IMAGE_MT_uvs"):
        bpy.types.IMAGE_MT_uvs.append(menu_func)
    elif hasattr(bpy.types, "UV_MT_uvs"):
        bpy.types.UV_MT_uvs.append(menu_func)
    print("✅ Scale & Snap to Clustered Palette Addon registered")


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types, "IMAGE_MT_uvs"):
        bpy.types.IMAGE_MT_uvs.remove(menu_func)
    elif hasattr(bpy.types, "UV_MT_uvs"):
        bpy.types.UV_MT_uvs.remove(menu_func)


if __name__ == "__main__":
    register()