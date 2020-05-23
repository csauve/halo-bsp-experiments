from reclaimer.hek.defs.sbsp import sbsp_def

# bsp3d_nodes = bsp.bsp3d_nodes.bsp3d_nodes_array
# bsp_planes = bsp.planes.planes_array

def fix_bsp(bsp_tag_path, report_only=False):
    tag = sbsp_def.build(filepath=bsp_tag_path)

    collision_bsp = tag.data.tagdata.collision_bsp.collision_bsp_array[0]
    bsp3d_nodes = collision_bsp.bsp3d_nodes.bsp3d_nodes_array

    def fix_node(bsp3d_node):
        if bsp3d_node.front_child == -1:
            bsp3d_node.front_child = bsp3d_node.back_child
        else if bsp3d_node.back_child == -1:
            bsp3d_node.back_child = bsp3d_node.front_child
        print("hey")

    fix_node(bsp3d_nodes[0])
    if not report_only:
        tag.serialize(backup=False, temp=False)

fix_bsp("/home/csauve/haloce/tags/levels/test/dangercanyon/dangercanyon.scenario_structure_bsp", True)
