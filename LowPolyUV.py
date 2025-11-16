bl_info = {
    "name": "LowPolyUV",
    "author": "Rainer Wahnsinn",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "UV Editor > UVs > LowPolyUV",
    "description": "Scale UV faces and snap face colors to a clustered palette",
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

        # Collapse all UVs to center
        for l in face.loops:
            l[uv_layer].uv = center.copy()

    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode=prev_mode)
    print(f"✅ Scaled and collapsed {len(selected_faces)} faces individually toward their centers")

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

def get_material_base_color(mat):
    """Extract base color from material node tree (optimized)"""
    if not mat or not mat.node_tree:
        return [1.0, 1.0, 1.0, 1.0]

    # Prefer Principled BSDF
    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            base_color = node.inputs.get('Base Color')
            if base_color and hasattr(base_color, 'default_value'):
                color = base_color.default_value
                if sum(color[:3]) > 0.01:
                    return list(color)
    
    # Fallback to Diffuse BSDF
    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_DIFFUSE':
            color = node.inputs.get('Color')
            if color and hasattr(color, 'default_value'):
                c = color.default_value
                if sum(c[:3]) > 0.01:
                    return list(c)

    # Fallback to material diffuse color
    if hasattr(mat, 'diffuse_color') and sum(mat.diffuse_color[:3]) > 0.01:
        return list(mat.diffuse_color)

    return [1.0, 1.0, 1.0, 1.0]

def cache_material_images(obj):
    """
    Cache all image textures used by the materials of the object.
    Returns a dictionary mapping material names to images.
    """
    material_images = {}
    for slot in obj.material_slots:
        mat = slot.material
        if mat and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    material_images[mat.name] = node.image
                    break
    return material_images

def sample_face_colors_safe(obj, max_colors=16):
    """
    Sample colors from all materials in the object
    """
    face_colors = []
    material_images = cache_material_images(obj)
    
    # Get all unique materials
    materials = []
    for slot in obj.material_slots:
        if slot.material and slot.material not in materials:
            materials.append(slot.material)
    
    # Sample from each material
    for mat in materials:
        image = material_images.get(mat.name)  # Get the image from the cache
        if image:
            # Sample from texture
            # You can use the image here for color sampling
            pass
        else:
            # Material without texture - use base color
            base_color = get_material_base_color(mat)
            if base_color != [1.0, 1.0, 1.0, 1.0]:  # If it's not pure white
                face_colors.append(base_color)
    
    return face_colors, material_images

def sample_face_colors_multimat(obj, max_colors=16):
    """
    Sample face colors for multi-material setup (optimized)
    """
    face_colors = []
    material_images = cache_material_images(obj)

    # Pre-cache all image nodes
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if not mat:
            continue
        # Using material_images to access textures
        image = material_images.get(mat.name)
        if image:
            # Process image
            pass

    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        return [], {}

    for face in bm.faces:
        if not face.select:
            continue

        mat_idx = face.material_index
        if mat_idx >= len(obj.material_slots):
            continue

        mat = obj.material_slots[mat_idx].material
        if not mat:
            continue

        image = material_images.get(mat.name)
        if image:
            width, height = image.size
            if width == 0 or height == 0:
                continue

            # Compute UV center once
            uvs = [l[uv_layer].uv.copy() for l in face.loops]
            center = sum(uvs, Vector((0, 0))) / len(uvs)
            center.x = max(0.0, min(1.0, center.x))
            center.y = max(0.0, min(1.0, center.y))

            px = int(center.x * (width - 1))
            py = int(center.y * (height - 1))
            idx = (py * width + px) * 4
            idx = max(0, min(idx, len(image.pixels) - 4))

            color = image.pixels[idx:idx + 4]

            # Fallback if dark/transparent
            if sum(color[:3]) < 0.01 or color[3] < 0.01:
                r = g = b = a = 0
                count = 0
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx = max(0, min(px + dx, width - 1))
                        ny = max(0, min(py + dy, height - 1))
                        nidx = (ny * width + nx) * 4
                        c = image.pixels[nidx:nidx + 4]
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += c[3]
                        count += 1
                color = [r / count, g / count, b / count, a / count]

            face_colors.append(color)
        else:
            base_color = get_material_base_color(mat)
            face_colors.append(base_color)

    bmesh.update_edit_mesh(obj.data)
    return face_colors, material_images

def snap_faces_to_palette(obj, max_colors=16, block_size=8):
    """
    Snap selected faces to a clustered palette (optimized single material path)
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
    
    material_images = cache_material_images(obj)

    if len(obj.material_slots) == 1:
        mat = obj.material_slots[0].material
        image = None
        if mat and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    image = node.image
                    break

        if image:
            width, height = image.size
            scale = 1.0
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
            palette_img, grid_size = create_square_palette(clustered_colors, name=obj.name+"_PaletteTexture", block_size=block_size)
            palette_cache = PaletteCache(clustered_colors, grid_size)

            for face, color in face_map.items():
                idx = palette_cache.closest_color_index(color)
                target_uv = palette_cache.positions[idx]
                for l in face.loops:
                    l[uv_layer].uv = target_uv.copy()

            bmesh.update_edit_mesh(obj.data)
            bpy.ops.object.mode_set(mode=prev_mode)
            obj.data.update()
            print("✅ Faces snapped (single-material fast path).")

            # Remove material
            obj.data.materials.clear()
            print("✅ Material removed")
            create_and_assign_palette_material(obj, palette_img)
            print(f"✅ New Material with Color Palette created.")
            return

    # Multi-material fallback
    snap_faces_to_palette_multimat(obj, max_colors=max_colors, block_size=block_size)

def snap_faces_to_palette_multimat(obj, max_colors=16, block_size=8):
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

    # Sample face colors
    face_colors, material_images = sample_face_colors_multimat(obj, max_colors=max_colors)
    
    if not face_colors:
        print("No face colors found")
        bpy.ops.object.mode_set(mode=prev_mode)
        return

    # Create clustered palette
    palette_img, grid_size = create_square_palette(face_colors, name=obj.name+"_PaletteTexture", block_size=block_size)
    print(f"Palette image created: {palette_img.name}, size: {palette_img.size}")

    # Create palette cache
    palette_cache = PaletteCache(face_colors, grid_size)

    # Snap faces to palette
    for face in bm.faces:
        if not face.select:
            continue

        mat_idx = face.material_index
        if mat_idx >= len(obj.material_slots):
            continue
            
        mat = obj.material_slots[mat_idx].material
        if not mat:
            continue

        # Get the face's color
        face_color = None
        
        # Try to get image for this material
        image = None
        if mat.name in material_images:
            image = material_images[mat.name]
        else:
            # Try to find image in this material's node tree
            if mat and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        image = node.image
                        material_images[mat.name] = image
                        break
        
        if image:
            # Sample from texture
            width, height = image.size
            if width == 0 or height == 0:
                continue
                
            # Get UV coordinates
            uvs = [l[uv_layer].uv.copy() for l in face.loops]
            center = sum(uvs, Vector((0, 0))) / len(uvs)
            center.x = max(0.0, min(1.0, center.x))
            center.y = max(0.0, min(1.0, center.y))
            
            px = int(center.x * (width - 1))
            py = int(center.y * (height - 1))
            idx = (py * width + px) * 4
            idx = max(0, min(idx, len(image.pixels) - 4))
            
            face_color = image.pixels[idx:idx + 4]
            
            # Fallback for dark/transparent pixels
            if sum(face_color[:3]) < 0.01 or face_color[3] < 0.01:
                r = g = b = a = 0
                count = 0
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx = max(0, min(px + dx, width - 1))
                        ny = max(0, min(py + dy, height - 1))
                        nidx = (ny * width + nx) * 4
                        c = image.pixels[nidx:nidx + 4]
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += c[3]
                        count += 1
                face_color = [r / count, g / count, b / count, a / count]
        else:
            # No texture - use base color
            face_color = get_material_base_color(mat)
        
        if face_color:
            # Snap to palette
            palette_idx = palette_cache.closest_color_index(face_color)
            target_uv = palette_cache.positions[palette_idx]

            for l in face.loops:
                l[uv_layer].uv = target_uv.copy()

    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode=prev_mode)
    obj.data.update()
    print(f"✅ Faces snapped to clustered palette (multi-material safe).")

    # Remove all materials
    if len(obj.material_slots) > 0:
        obj.data.materials.clear()
        print("✅ All materials removed")
    
    # Create and assign new material
    create_and_assign_palette_material(obj, palette_img)
    print(f"✅ New Material with Color Palette created.")

def create_square_palette(colors, name="PaletteTexture", block_size=8):
    """
    Create a square palette texture from a list of colors
    """
    import math
    
    # Calculate grid dimensions
    grid_size = max(1, math.ceil(math.sqrt(len(colors))))
    
    # Create image
    width = grid_size * block_size
    height = grid_size * block_size
    
    # Create pixel data
    pixels = []
    for y in range(height):
        for x in range(width):
            # Calculate which color block this pixel belongs to
            block_y = y // block_size
            block_x = x // block_size
            
            if block_y < grid_size and block_x < grid_size:
                color_idx = block_y * grid_size + block_x
                if color_idx < len(colors):
                    color = colors[color_idx]
                else:
                    color = [1.0, 1.0, 1.0, 1.0]
            else:
                color = [1.0, 1.0, 1.0, 1.0]
            
            pixels.extend(color)
    
    # Create image
    img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
    img.pixels.foreach_set(pixels)
    img.update()
    
    return img, grid_size

def create_and_assign_palette_material(obj, palette_img, use_metallic=False, use_flat_shading=True):
    """
    Create a new material with the palette image assigned as a texture.
    Appends it to the object's material slots instead of replacing the first.
    """
    # Create new material
    mat = bpy.data.materials.new(name="PaletteMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # Create image texture node
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.image = palette_img
    tex_node.location = (-300, 0)

    # Create Principled BSDF
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    
    # Set metallic value
    bsdf.inputs['Metallic'].default_value = 1.0 if use_metallic else 0.0

    # Create Material Output
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)

    # Link nodes
    links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    # Append the new material to the object
    obj.data.materials.append(mat)
    
    if use_flat_shading:
        prev_mode = obj.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.shade_flat()
        bpy.ops.object.mode_set(mode=prev_mode)
        print("✅ Flat shading applied")
    
    print(f"✅ Appended new material '{mat.name}' with palette image '{palette_img.name}'")
    print(f"✅ Metallic: {'ON' if use_metallic else 'OFF'}")
    print(f"✅ Flat Shading: {'ON' if use_flat_shading else 'OFF'}")

class PaletteCache:
    def __init__(self, colors, grid_size):
        self.colors = colors
        self.grid_size = grid_size
        self.positions = []
        for i, color in enumerate(colors):
            row = i // grid_size
            col = i % grid_size
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

class UV_OT_ScaleAndSnapPalette(bpy.types.Operator):
    bl_idname = "uv.lowpolyuv"
    bl_label = "LowPolyUV"
    bl_options = {'REGISTER', 'UNDO'}

    scale_factor: bpy.props.FloatProperty(
        name="UV Face Scale",
        default=0,
        min=0.0,
        max=1.0,
        description="Scale each UV face before snapping"
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
    
    use_metallic: bpy.props.BoolProperty(
        name="Metallic",
        description="Enable metallic shader",
        default=False
    )
    
    use_flat_shading: bpy.props.BoolProperty(
        name="Flat Shading",
        description="Use flat shading",
        default=True
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "scale_factor")
        layout.prop(self, "max_colors")
        layout.prop(self, "use_metallic")
        layout.prop(self, "use_flat_shading")
        layout.prop(self, "block_size")
        layout.prop(self, "use_downscale")
        if self.use_downscale:
            layout.prop(self, "downscale_max")

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object!")
            return {'CANCELLED'}
        scale_faces_to_center(self.scale_factor)
        snap_faces_to_palette(obj, max_colors=self.max_colors, block_size=self.block_size)
        self.report(
            {'INFO'},
            f"✅ UVs scaled and snapped ({'single-material fast path' if len(obj.material_slots)==1 else 'multi-material'})"
        )
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(UV_OT_ScaleAndSnapPalette.bl_idname, icon='COLOR')


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