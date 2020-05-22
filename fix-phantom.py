from reclaimer.hek.defs.sbsp import sbsp_def

bsp_path = "/home/csauve/haloce/tags/levels/test/dangercanyon/dangercanyon.scenario_structure_bsp"
tag = sbsp_def.build(filepath=bsp_path)

bsp = tag.data.tagdata
bsp3d_nodes = bsp.collision_bsp.collision_bsp_array[0].bsp3d_nodes.bsp3d_nodes_array
bsp_planes = bsp.collision_bsp.collision_bsp_array[0].planes.planes_array

def fix_c():
    bsp3d_nodes[8198].back_child = 8195

def fix_b():
    bsp3d_nodes[8197].front_child = bsp3d_nodes[8198].front_child

def fix_a():
    # get the parent of the ramp leaf
    parent_node = bsp3d_nodes[8197]

    # create a new bsp3d node to hold the original parent's contents
    bsp3d_nodes.extend(1)
    child_index = len(bsp3d_nodes) - 1
    child_node = bsp3d_nodes[child_index]
    child_node.plane = parent_node.plane
    child_node.front_child = parent_node.front_child
    child_node.back_child = parent_node.back_child

    # point the parent to its duplicate
    parent_node.plane = 1535
    parent_node.back_child = child_index
    parent_node.front_child = 8195

fix_c()

tag.serialize(backup=False, temp=False)
