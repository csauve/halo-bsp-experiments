from reclaimer.hek.defs.sbsp import sbsp_def

bsp_path = "/home/csauve/haloce/tags/levels/test/dangercanyon/dangercanyon.scenario_structure_bsp"
tag = sbsp_def.build(filepath=bsp_path)

bsp = tag.data.tagdata
bsp_verts = bsp.collision_bsp.collision_bsp_array[0].vertices.vertices_array
bsp_planes = bsp.collision_bsp.collision_bsp_array[0].planes.planes_array

def mess_up_verts():
    for vert in bsp_verts:
        vert.x = 0.0
        vert.y = 0.0
        vert.z = 0.0

def mess_up_planes():
    for plane in bsp_planes:
        plane.i = 0.0
        plane.j = 0.0
        plane.k = 1.0
        plane.d = -4.0

def offset_planes():
    for plane in bsp_planes:
        plane.i -= 0.001

# mess_up_verts()
# mess_up_planes()
offset_planes()

tag.serialize(backup=False, temp=False)
