"""
ArtiverseObjectFactory — wraps a pre-built segmented GLB as an Infinigen AssetFactory.

Configured via gin -p overrides before running generate_indoors:
    ArtiverseObjectFactory.glb_path    = "/path/to/model.segmented.glb"
    ArtiverseObjectFactory.dimensions  = [0.8, 0.7, 1.6]   # [width, depth, height] metres
    ArtiverseObjectFactory.category    = "oven"

fpModel assets are metric-scale and correctly oriented (Y-up / GLTF).
Blender's GLTF importer handles Y-up → Z-up conversion automatically.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import gin
import numpy as np

from infinigen.core.placement.factory import AssetFactory
from infinigen.core.util import blender as butil
from infinigen.core.util.math import FixedSeed

logger = logging.getLogger(__name__)


@gin.configurable
class ArtiverseObjectFactory(AssetFactory):
    """
    Loads a single Artiverse segmented GLB as an Infinigen factory.

    The factory is injected into the constraint solver via semantics.py when
    _artiverse_semantic_role.role is set to a non-empty Semantics key.
    """

    def __init__(
        self,
        factory_seed: int,
        coarse: bool = False,
        glb_path: str = "",
        dimensions: list = None,
        category: str = "object",
        front_rotation_z: float = 0.0,
    ):
        super().__init__(factory_seed, coarse=coarse)
        self.glb_path = Path(glb_path)
        self.category = category
        # [width, depth, height] in metres — sizes the placeholder bbox
        self.dims = dimensions if dimensions is not None else [1.0, 1.0, 1.0]
        # Extra Z-rotation (radians) applied after GLB import to align the object's
        # front face with Infinigen's +Y front convention.  Default 0 is correct for
        # most fpModel assets (GLTF -Z forward → Blender +Y after Y-up conversion).
        # Set to math.pi (≈3.14159) to flip objects exported with +Z forward, or to
        # math.pi/2 for 90° L-shaped corner variants.
        self.front_rotation_z = front_rotation_z

        if not glb_path:
            raise ValueError(
                "ArtiverseObjectFactory requires glb_path set via gin:\n"
                "  ArtiverseObjectFactory.glb_path = '/path/to/model.segmented.glb'"
            )
        if not self.glb_path.exists():
            raise FileNotFoundError(
                f"ArtiverseObjectFactory: GLB not found: {self.glb_path}"
            )

        logger.info(
            f"ArtiverseObjectFactory: category={category} "
            f"glb={self.glb_path.name} dims={self.dims}"
        )

    # ------------------------------------------------------------------
    # AssetFactory interface
    # ------------------------------------------------------------------

    def create_placeholder(self, **kwargs):
        """
        Return an axis-aligned bounding box for the constraint solver.
        Sized to match the GLB so furniture spacing is realistic.
        """
        import bpy
        w, d, h = self.dims
        obj = butil.spawn_cube(size=1.0)
        obj.scale = (w, d, h)
        butil.apply_transform(obj, scale=True)
        obj.name = f"artiverse_placeholder_{self.category}"
        return obj

    def create_asset(self, **params):
        """Import the segmented GLB and return the root object."""
        import bpy

        logger.info(
            f"ArtiverseObjectFactory.create_asset: importing {self.glb_path}"
        )

        with FixedSeed(self.factory_seed):
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(
                filepath=str(self.glb_path),
                import_shading="NORMALS",
            )
            new_objs = list(set(bpy.data.objects) - before)

        if not new_objs:
            raise RuntimeError(
                f"ArtiverseObjectFactory: GLTF import produced no objects: "
                f"{self.glb_path}"
            )

        # Return the root (parentless among newly imported objects)
        roots = [o for o in new_objs if o.parent not in new_objs]
        root = roots[0] if roots else new_objs[0]
        root.name = f"artiverse_{self.category}"

        # Apply front-alignment rotation around Z so the object's front face
        # coincides with Infinigen's +Y convention (used by accessibility costs
        # and the against_wall constraint solver).
        if self.front_rotation_z != 0.0:
            root.rotation_euler[2] += self.front_rotation_z

        return root
