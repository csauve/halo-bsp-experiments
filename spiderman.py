from reclaimer.hek.defs.sbsp import sbsp_def
import argparse

def spiderman(bsp_path):
    tag = sbsp_def.build(filepath=bsp_path)

    bsp = tag.data.tagdata
    bsp_surfaces = bsp.collision_bsp.collision_bsp_array[0].surfaces.surfaces_array

    for surface in bsp_surfaces:
        surface.flags.climbable = True

    tag.serialize(backup=False, temp=False)

parser = argparse.ArgumentParser()
parser.add_argument("bsp", help="Path to the BSP file to modify")
args = parser.parse_args()
fix_bsp(args.bsp)
