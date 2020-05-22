from reclaimer.hek.defs.sbsp import sbsp_def
from inspect import getmembers
import collada
import numpy as np
from scipy.spatial.transform import Rotation as R

#https://github.com/Sigmmma/reclaimer/blob/master/reclaimer/hek/defs/coll.py
bsp_path = "/home/csauve/haloce/tags/levels/test/dangercanyon/dangercanyon.scenario_structure_bsp"
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

vert_floats = [[v.x, v.y, v.z] for v in bsp_verts]
normal_floats = [[p.i, p.j, p.k] for p in bsp_planes]

mtl_effect_surface = collada.material.Effect("mtl_effect_surface", [], "phong", diffuse=(0.5, 0.5, 0.5), specular=(0, 1, 0))
mtl_surface = collada.material.Material("mtl_surface", "mtl_surface", mtl_effect_surface)
dae.effects.append(mtl_effect_surface)
dae.materials.append(mtl_surface)

mtl_effect_surface_flagged = collada.material.Effect("mtl_effect_surface_flagged", [], "phong", diffuse=(1.0, 0.5, 0.5), specular=(0, 1, 0))
mtl_surface_flagged = collada.material.Material("mtl_surface_flagged", "mtl_surface_flagged", mtl_effect_surface_flagged)
dae.effects.append(mtl_effect_surface_flagged)
dae.materials.append(mtl_surface_flagged)

sfc_count = 0

def gen_surface_geometry(bsp_vert_indices, bsp_plane_index, surface_name):
    vert_src_name = surface_name + "_verts"
    surface_vert_floats = np.array([vert_floats[v] for v in bsp_vert_indices]).flatten()
    vert_src = collada.source.FloatSource(vert_src_name, surface_vert_floats, ("X", "Y", "Z"))

    mtl_name = "mtl_surface"
    if bsp_plane_index < 0 or bsp_plane_index >= len(normal_floats):
        bsp_plane_index = bsp_plane_index & 0x7FFFFFFF
        mtl_name = "mtl_surface_flagged"
        # print("Flagged plane index? " + str(bsp_plane_index))

    normal_src_name = surface_name + "_normals"
    surface_normal_floats = np.array(normal_floats[bsp_plane_index])
    normal_src = collada.source.FloatSource(normal_src_name, surface_normal_floats, ("X", "Y", "Z"))

    input_list = collada.source.InputList()
    input_list.addInput(0, "VERTEX", "#" + vert_src_name)
    input_list.addInput(1, "NORMAL", "#" + normal_src_name)

    num_verts = len(bsp_vert_indices)
    geom = collada.geometry.Geometry(dae, surface_name, surface_name, [vert_src, normal_src])
    indices = np.array([[v, 0] for v in range(0, num_verts)]).flatten()
    vcounts = np.array([num_verts])
    poly = geom.createPolylist(indices, vcounts, input_list, mtl_name)
    matnode = collada.scene.MaterialNode("mtl", mtl_surface, inputs=[])
    geom.primitives.append(poly)
    dae.geometries.append(geom)
    global sfc_count
    sfc_count = sfc_count + 1
    return collada.scene.GeometryNode(geom, [matnode])

def gen_surface_node(bsp_surface_index, node_name):
    bsp_surface = bsp_surfaces[bsp_surface_index]
    first_edge = bsp_edges[bsp_surface.first_edge]
    bsp_vert_indices = []
    curr_edge = first_edge

    while True:
        forward = curr_edge.left_surface == bsp_surface_index
        bsp_vert_indices.append(curr_edge.start_vertex if forward else curr_edge.end_vertex)
        next_edge_index = curr_edge["forward_edge" if forward else "reverse_edge"]
        if next_edge_index == bsp_surface.first_edge:
            break
        curr_edge = bsp_edges[next_edge_index]
    geometry_node = gen_surface_geometry(bsp_vert_indices, bsp_surface.plane, node_name)
    return collada.scene.Node(node_name, children=[geometry_node])

def gen_bsp2d_node(bsp2d_node_index):
    if bsp2d_node_index & 0x80000000 != 0:
        bsp_surface_index = bsp2d_node_index & 0x7FFFFFFF
        return gen_surface_node(bsp_surface_index, "surface_" + str(bsp_surface_index))
    else:
        bsp2d_node = bsp2d_nodes[bsp2d_node_index]
        children = [
            gen_bsp2d_node(bsp2d_node.left_child),
            gen_bsp2d_node(bsp2d_node.right_child)
        ]
        return collada.scene.Node("bsp2d_node_" + str(bsp2d_node_index), children=children)

def gen_bsp2d_reference_node(bsp2d_reference_index):
    bsp2d_reference = bsp2d_references[bsp2d_reference_index]
    return gen_bsp2d_node(bsp2d_reference.bsp2d_node)

def gen_leaf_node(bsp_leaf_index):
    bsp_leaf = bsp_leaves[bsp_leaf_index]
    bsp2d_ref_count = bsp_leaf.bsp2d_reference_count
    bsp2d_ref_first = bsp_leaf.first_bsp2d_reference
    children = []
    if bsp2d_ref_count > 0:
        children = [gen_bsp2d_reference_node(i) for i in range(bsp2d_ref_first, bsp2d_ref_first + bsp2d_ref_count)]
    return collada.scene.Node("leaf_" + str(bsp_leaf_index), children=children)

def gen_plane_geometry_node(plane_index):
    matching_bsp_surface_index = None
    for i, bsp_surface in enumerate(bsp_surfaces):
        if bsp_surface.plane & 0x7FFFFFFF == plane_index & 0x7FFFFFFF:
            matching_bsp_surface_index = i
    if matching_bsp_surface_index is None:
        return None
    return gen_surface_node(matching_bsp_surface_index, "plane_" + str(plane_index))

def gen_bsp3d_node(bsp3d_node_index):
    if bsp3d_node_index == -1:
        return None
    elif bsp3d_node_index & 0x80000000 != 0:
        bsp_leaf_index = bsp3d_node_index & 0x7FFFFFFF
        return gen_leaf_node(bsp_leaf_index)
    else:
        bsp3d_node = bsp3d_nodes[bsp3d_node_index]
        bsp3d_node_name = "bsp3d_node_" + str(bsp3d_node_index)
        back_child_node = gen_bsp3d_node(bsp3d_node.back_child)
        front_child_node = gen_bsp3d_node(bsp3d_node.front_child)
        plane = gen_plane_geometry_node(bsp3d_node.plane)

        children = []

        if plane is not None:
            children.append(plane)
        if back_child_node is not None:
            children.append(back_child_node)
        if front_child_node is not None:
            children.append(front_child_node)
        return collada.scene.Node(bsp3d_node_name, children=children)

#https://pycollada.readthedocs.io/en/latest/creating.html
root_node = gen_bsp3d_node(0)
scene = collada.scene.Scene("bsp_scene", [root_node])
dae.scenes.append(scene)
dae.scene = scene
dae.write("./bsp.dae")

print("BSP surfaces: " + str(len(bsp_surfaces)))
print("Gen surfaces: " + str(sfc_count))
