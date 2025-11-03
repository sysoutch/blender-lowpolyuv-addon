# LowPolyUV (Blender Addon)

[![Blender Version](https://img.shields.io/badge/Blender-3.0%2B-blue.svg)](https://www.blender.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**Scale UV faces and snap face colors to a clustered palette inside Blender.**  
This addon is designed for artists who want to simplify texture colors and align UVs with a limited palette quickly.

## Features

- Scale selected UV faces individually.
- Sample face colors from the active material’s image texture.
- Optionally downscale the image for faster color sampling.
- Cluster colors using **k-means** into a limited palette.
- Snap UVs to a generated palette texture.
- User-friendly Blender operator with undo support.
- Optional checkbox to choose whether to use the downscaled texture for sampling.

## Screenshots

**Your UV Map**

![Original Texture](https://github.com/sysoutch/blender-lowpolyuv-addon/blob/main/before.png?raw=true)

**UVLowPoly UV Map:**

![Downscaled Texture](https://github.com/sysoutch/blender-lowpolyuv-addon/blob/main/after.png?raw=true)

**More:**

![W.W.](ww_screen.png)

## Installation

1. Download the repository as a `.zip` file.
2. Open Blender.
3. Go to `Edit → Preferences → Add-ons → Install`.
4. Select the `.zip` file and click `Install Add-on`.
5. Enable the addon in the preferences.
6. Access it in the **UV Editor → UVs → Scale & Snap Palette**.

## Usage

![Downscaled Texture](https://github.com/sysoutch/blender-lowpolyuv-addon/blob/main/lowpolyuv_screen.png)

1. Select a mesh object with UVs and an image texture.
2. Enter Edit Mode and select the faces you want to process.
3. Open the operator: `UV Editor → UVs → Scale & Snap Palette`.
4. Adjust parameters:
   - **UV Island Scale**: scales each selected UV island.
   - **Max Colors**: maximum number of colors in the generated palette.
   - **Block Size**: size of each color block in the palette.
   - **Use Downscaled Sampling**: (checkbox) whether to sample colors from a scaled-down image for speed.
5. Click **OK** to scale UV islands and snap face colors to the clustered palette.

## How It Works

1. **Scale UV islands:**  
   Each selected UV island is scaled around its center by the user-defined factor. This helps in aligning the UVs better with the palette blocks.

2. **Sample face colors:**  
   The addon reads the colors of each face from the material’s image texture. If downscaling is enabled, it uses a smaller version of the image for faster computation.

3. **Cluster colors using k-means:**  
   K-means is an algorithm that groups colors into `k` clusters by minimizing the distance between colors and cluster centroids.  
   Steps:
   - Start with `k` random colors as initial cluster centers.
   - Assign each color to the nearest cluster.
   - Recalculate cluster centers as the average of assigned colors.
   - Repeat for several iterations until convergence.
   
   This produces a reduced set of representative colors.

4. **Generate palette and snap UVs:**  
   The clustered colors are laid out in a square texture. Each face’s UVs are moved to the corresponding palette block, effectively “snapping” the face color to the closest palette color.

## Example Result

| Original | Snapped Palette |
|----------|----------------|
| ![Original](images/original_texture.png) | ![Snapped](images/palette_result.png) |

## Notes

- Works with **Blender 3.0+**.
- Only works with **mesh objects**.
- If no image texture is found, the addon will skip color snapping.
- Downscaled sampling improves performance for large textures but may slightly alter color precision.

## License

This addon is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.  
You are free to use, modify, and distribute it, **but any derivative work must also be GPL-3.0**.  
See the [LICENSE](LICENSE) file for full details.

## Contributing

Fork the repo, make your changes, and submit a pull request.  
Please keep modifications under GPL-3.0 and credit the original author (Rainer).