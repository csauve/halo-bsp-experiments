from reclaimer.hek.defs.sbsp import sbsp_def
from inspect import getmembers
import collada
import numpy as np
from scipy.spatial.transform import Rotation as R

#https://github.com/Sigmmma/reclaimer/blob/master/reclaimer/hek/defs/coll.py
bsp_path = "/home/csauve/haloce/tags/levels/test/bloodgulch/bloodgulch.scenario_structure_bsp"
bsp = sbsp_def.build(filepath=bsp_path).data.tagdata
bsp3d_nodes = bsp.collision_bsp.collision_bsp_array[0].bsp3d_nodes.bsp3d_nodes_array
bsp2d_nodes = bsp.collision_bsp.collision_bsp_array[0].bsp2d_nodes.bsp2d_nodes_array
bsp2d_references = bsp.collision_bsp.collision_bsp_array[0].bsp2d_references.bsp2d_references_array
bsp_leaves = bsp.collision_bsp.collision_bsp_array[0].leaves.leaves_array
bsp_planes = bsp.collision_bsp.collision_bsp_array[0].planes.planes_array
bsp_surfaces = bsp.collision_bsp.collision_bsp_array[0].surfaces.surfaces_array
bsp_edges = bsp.collision_bsp.collision_bsp_array[0].edges.edges_array
bsp_verts = bsp.collision_bsp.collision_bsp_array[0].vertices.vertices_array

dae = collada.Collada()

# def gen_plane_geometry_node(plane_index, bsp3d_node_index):
#     plane_name = "plane_" + str(bsp3d_node_index)
#     bsp_plane = bsp_planes[plane_index]
#     bsp_plane_normal = [bsp_plane.i, bsp_plane.j, bsp_plane.k]
#     init_normal = [0., 0, 1]
#     rot_axis = np.cross(bsp_plane_normal, init_normal)
#     rot_angle = None
#     rot_matrix = R.from_rotvec()
#     plane_geom = collada.geometry.Geometry(dae, plane_name, plane_name, [vert_src, normal_src], double_sided=True)
#     plane_geometry_node = collada.scene.GeometryNode(plane_geom)
#     return plane_geometry_node

vert_floats = [[v.x, v.y, v.z] for v in bsp_verts]
normal_floats = [[p.i, p.j, p.k] for p in bsp_planes]

vert_src = collada.source.FloatSource("vertices", np.array(vert_floats).flatten(), ("X", "Y", "Z"))
normal_src = collada.source.FloatSource("normals", np.array(normal_floats).flatten(), ("X", "Y", "Z"))

mtl_effect_surface = collada.material.Effect("mtl_effect_surface", [], "phong", diffuse=(0.5, 0.5, 0.5), specular=(0, 1, 0))
mtl_surface = collada.material.Material("mtl_surface", "mtl_surface", mtl_effect_surface)
dae.effects.append(mtl_effect_surface)
dae.materials.append(mtl_surface)

def gen_surface_geometry(bsp_vert_indices, bsp_plane_index, surface_name):
    print(surface_name)
    geom = collada.geometry.Geometry(dae, surface_name, surface_name, [vert_src, normal_src])
    input_list = collada.source.InputList()
    input_list.addInput(0, "VERTEX", "#vertices")
    input_list.addInput(1, "NORMAL", "#normals")
    indices = np.array([[v, bsp_plane_index] for v in bsp_vert_indices]).flatten()
    vcounts = np.array([len(bsp_vert_indices)])
    poly = geom.createPolylist(indices, vcounts, input_list, "mtl_surface")
    matnode = collada.scene.MaterialNode("mtl_surface", mtl_surface, inputs=[])
    geom.primitives.append(poly)
    dae.geometries.append(geom)
    return collada.scene.GeometryNode(geom, [matnode])

def gen_surface_node(bsp_surface_index):
    bsp_surface = bsp_surfaces[bsp_surface_index]
    first_edge = bsp_edges[bsp_surface.first_edge]
    edges = [first_edge]
    while True:
        curr_edge = edges[-1]
        forward = curr_edge.left_surface == bsp_surface_index
        next_edge_index = curr_edge["forward_edge" if forward else "reverse_edge"]
        if next_edge_index == bsp_surface.first_edge:
            break
        edges.append(bsp_edges[next_edge_index])
    bsp_vert_indices = [e.start_vertex for e in edges]
    return gen_surface_geometry(bsp_vert_indices, bsp_surface.plane, "surface_" + str(bsp_surface_index))

def gen_bsp2d_node(bsp2d_node_index):
    if bsp2d_node_index & 0x80000000 != 0:
        bsp_surface_index = bsp2d_node_index & 0x7FFFFFFF
        return gen_surface_node(bsp_surface_index)
    else:
        bsp2d_node = bsp2d_nodes[bsp2d_node_index]
        left_child_node = gen_bsp2d_node(bsp2d_node.left_child)
        right_child_node = gen_bsp2d_node(bsp2d_node.right_child)
        children = []
        if left_child_node is not None:
            children.append(left_child_node)
        if right_child_node is not None:
            children.append(right_child_node)
        return collada.scene.Node("bsp2d_node_" + str(bsp2d_node_index), children=children)

def gen_bsp2d_reference_node(bsp2d_reference_index):
    bsp2d_reference = bsp2d_references[bsp2d_reference_index]
    return gen_bsp2d_node(bsp2d_reference.bsp2d_node)

def gen_leaf_node(bsp_leaf_index):
    bsp_leaf = bsp_leaves[bsp_leaf_index]
    bsp2d_ref_count = bsp_leaf.bsp2d_reference_count
    bsp2d_ref_first = bsp_leaf.first_bsp2d_reference
    children = [gen_bsp2d_reference_node(i) for i in range(bsp2d_ref_first, bsp2d_ref_first + bsp2d_ref_count)]
    return collada.scene.Node("leaf_" + str(bsp_leaf_index), children=children)

def gen_bsp3d_node(bsp3d_node_index):
    if bsp3d_node_index == -1:
        return None
    elif bsp3d_node_index & 0x80000000 != 0:
        bsp_leaf_index = bsp3d_node_index & 0x7FFFFFFF
        return gen_leaf_node(bsp_leaf_index)
    else:
        bsp3d_node = bsp3d_nodes[bsp3d_node_index]
        back_child_node = gen_bsp3d_node(bsp3d_node.back_child)
        front_child_node = gen_bsp3d_node(bsp3d_node.front_child)

        children = []
        # children.append(gen_plane_geometry_node(bsp3d_node.plane, bsp3d_node_index))
        if back_child_node is not None:
            children.append(back_child_node)
        if front_child_node is not None:
            children.append(front_child_node)
        return collada.scene.Node("bsp3d_node_" + str(bsp3d_node_index), children=children)

#https://pycollada.readthedocs.io/en/latest/creating.html
root_node = gen_bsp3d_node(0)
scene = collada.scene.Scene("bsp_scene", [root_node])
dae.scenes.append(scene)
dae.scene = scene
dae.write("./bsp.dae")
