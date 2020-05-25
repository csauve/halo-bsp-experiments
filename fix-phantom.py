from reclaimer.hek.defs.sbsp import sbsp_def
import numpy as np

# check for numbers "close enough" to zero to account for rounding/precision issues
def zeroish(n, threshold):
    return abs(n) < threshold

# the following few math functions before fix_bsp expect numpy types
def to_np_point(point):
    return np.array([point.x, point.y, point.z])

def to_np_plane(plane, is_front):
    normal = np.array([plane.i, plane.j, plane.k])
    dist = plane.d
    return (normal, dist) if is_front else (normal * -1.0, dist * -1.0)

def point_cmp_plane(point, plane):
    plane_normal, plane_dist = plane
    plane_origin = plane_normal * plane_dist
    point_vec = point - plane_origin
    product = np.dot(point_vec, plane_normal)
    return product

def dist(point_a, point_b):
    offset = point_b - point_a
    return np.sqrt(offset.dot(offset))

# https://en.wikipedia.org/wiki/Line%E2%80%93plane_intersection
def t_line_plane_intersection(start, end, plane):
    plane_normal, plane_dist = plane
    plane_origin = plane_normal * plane_dist
    line_offset = end - start
    line_dot_normal = np.dot(line_offset, plane_normal)
    if line_dot_normal == 0.0:
        return (None, None)
    t = np.dot((plane_origin - start), plane_normal) / line_dot_normal
    entering = line_dot_normal > 0.0
    return (None, None) if t > 1.0 or t < 0.0 else (t, entering)

def lerp_points(start_point, end_point, t):
    offset = end_point - start_point
    return start_point + offset * t

def fix_bsp(bsp_tag_path, report_only=False):
    tag = sbsp_def.build(filepath=bsp_tag_path)

    collision_bsp = tag.data.tagdata.collision_bsp.collision_bsp_array[0]
    bsp3d_nodes = collision_bsp.bsp3d_nodes.bsp3d_nodes_array
    bsp2d_nodes = collision_bsp.bsp2d_nodes.bsp2d_nodes_array
    bsp2d_refs = collision_bsp.bsp2d_references.bsp2d_references_array
    leaves = collision_bsp.leaves.leaves_array
    planes = collision_bsp.planes.planes_array
    surfaces = collision_bsp.surfaces.surfaces_array
    edges = collision_bsp.edges.edges_array
    verts = collision_bsp.vertices.vertices_array

    def gather_bsp2d_node_surfaces(bsp2d_node_index):
        if bsp2d_node_index & 0x80000000 != 0:
            surface_index = bsp2d_node_index & 0x7FFFFFFF
            return [surface_index]
        bsp2d_node = bsp2d_nodes[bsp2d_node_index]
        left_surfaces = gather_bsp2d_node_surfaces(bsp2d_node.left_child)
        right_surfaces = gather_bsp2d_node_surfaces(bsp2d_node.right_child)
        return left_surfaces + right_surfaces

    def gather_bsp2d_ref_surfaces(bsp2d_ref_index):
        bsp2d_ref = bsp2d_refs[bsp2d_ref_index]
        return gather_bsp2d_node_surfaces(bsp2d_ref.bsp2d_node)

    def gather_leaf_surfaces(leaf_index):
        leaf = leaves[leaf_index]
        bsp2d_ref_count = leaf.bsp2d_reference_count
        bsp2d_ref_first = leaf.first_bsp2d_reference
        surfaces = []
        for r in range(bsp2d_ref_first, bsp2d_ref_first + bsp2d_ref_count):
            surfaces += gather_bsp2d_ref_surfaces(r)
        return surfaces

    def gather_bsp3d_node_surfaces(bsp3d_node_index):
        if bsp3d_node_index == -1:
            return []
        elif bsp3d_node_index & 0x80000000 != 0:
            leaf_index = bsp3d_node_index & 0x7FFFFFFF
            return gather_leaf_surfaces(leaf_index)
        bsp3d_node = bsp3d_nodes[bsp3d_node_index]
        front_surfaces = gather_bsp3d_node_surfaces(bsp3d_node.front_child)
        back_surfaces = gather_bsp3d_node_surfaces(bsp3d_node.back_child)
        return front_surfaces + back_surfaces

    def get_extended_surface_outer_edges(plane_surface_index, surface_indices):
        unvisited_surface_indices = set([plane_surface_index])
        visited_surface_indices = set()
        outer_edge_indices = set()
        surface_indices = set(surface_indices)

        while len(unvisited_surface_indices) > 0:
            surface_index = unvisited_surface_indices.pop()
            visited_surface_indices.add(surface_index)

            surface = surfaces[surface_index]
            curr_edge_index = surface.first_edge

            while True:
                curr_edge = edges[curr_edge_index]
                forward = curr_edge.left_surface == surface_index
                neighbour_surface_index = curr_edge.right_surface if forward else curr_edge.left_surface
                if neighbour_surface_index in surface_indices:
                    if neighbour_surface_index not in visited_surface_indices:
                        unvisited_surface_indices.add(neighbour_surface_index)
                else:
                    outer_edge_indices.add(curr_edge_index)
                next_edge_index = curr_edge["forward_edge" if forward else "reverse_edge"]
                if next_edge_index == surface.first_edge:
                    break
                curr_edge_index = next_edge_index

        return outer_edge_indices


    # True if the edge passes through the convex polyhedron defined by node
    # plane half-spaces. It is not considered inside of it is co-planar.
    # See: http://web.cse.ohio-state.edu/~parent.1/classes/681/Lectures/14.ObjectIntersection.pdf
    def edge_inside_polyhedron(edge_index, halfspaces):
        edge = edges[edge_index]
        edge_start = to_np_point(verts[edge.start_vertex])
        edge_end = to_np_point(verts[edge.end_vertex])

        t_entry_max = None
        t_exit_min = None

        for plane_index, is_front, _bsp3d_node in halfspaces:
            plane = to_np_plane(planes[plane_index & 0x7FFFFFFF], is_front)
            start_cmp = point_cmp_plane(edge_start, plane)
            end_cmp = point_cmp_plane(edge_end, plane)
            # If line is co-planar with one of the planes it cannot be inside the
            # volume. This thredshold is super sensitive... too high and we miss
            # phantom BSP on very similar planes to parent node planes, but too
            # low and we get false positive phantom BSP from low precision.
            if zeroish(start_cmp, 0.0001) and zeroish(end_cmp, 0.0001):
                return False
            t_intersection, entering = t_line_plane_intersection(edge_start, edge_end, plane)
            if t_intersection is not None:
                if entering:
                    if t_entry_max is None or t_intersection > t_entry_max:
                        t_entry_max = t_intersection
                else:
                    if t_exit_min is None or t_intersection < t_exit_min:
                        t_exit_min = t_intersection

        # If we miss the planes then there's no way it can be interecting the volume
        if t_entry_max is None or t_exit_min is None:
            return False

        entry_point = lerp_points(edge_start, edge_end, t_entry_max)
        exit_point = lerp_points(edge_start, edge_end, t_exit_min)

        # If entry and exit are essentially the same point, ignore
        if zeroish(dist(entry_point, exit_point), 0.05):
            return False

        # We still need to check if the intersection points are outside the volume
        for plane_index, is_front, _bsp3d_node in halfspaces:
            plane = to_np_plane(planes[plane_index & 0x7FFFFFFF], is_front)
            entry_cmp = point_cmp_plane(entry_point, plane)
            exit_cmp = point_cmp_plane(exit_point, plane)
            if not zeroish(entry_cmp, 0.00001) and entry_cmp < 0.0:
                return False
            if not zeroish(exit_cmp, 0.00001) and exit_cmp < 0.0:
                return False

        return t_entry_max < t_exit_min

    # Determines if the plane is not obstructed by the surfaces under this node
    def plane_unoccluded(dividing_plane_index, child_bsp3d_node_index, bsp3d_node_index, parent_halfspaces):
        # meaning of flagged plane index is unknown...
        if dividing_plane_index & 0x80000000:
            dividing_plane_index = dividing_plane_index & 0x7FFFFFFF
            print("UNEXPECTED FLAGGED PLANE: Converting to " + str(dividing_plane_index))

        # first we need the set of all surface indices under this node
        surface_indices = gather_bsp3d_node_surfaces(child_bsp3d_node_index)

        # Next, identify which surface was used to define parent node's plane
        plane_surface_index = None
        for s in surface_indices:
            surface = surfaces[s]
            if surface.plane & 0x7FFFFFFF == dividing_plane_index:
                plane_surface_index = s

        if plane_surface_index is None:
            return False

        # Get the bounding edges of the extended surface which was used for the plane
        outer_edge_indices = get_extended_surface_outer_edges(plane_surface_index, surface_indices)

        # todo: ignore cases where surrounding faces are convex

        # If any of the bounding edges pass inside the node's space, then the parent plane is exposed
        for outer_edge_index in outer_edge_indices:
            if edge_inside_polyhedron(outer_edge_index, parent_halfspaces):
                print("Phantom BSP detected: plane={} surface={} edge={} leaf={} path={}/{}".format(
                    dividing_plane_index,
                    plane_surface_index,
                    outer_edge_index,
                    child_bsp3d_node_index & 0x7FFFFFFF,
                    "/".join([str(n & 0x7FFFFFFF) for (_p, _f, n) in parent_halfspaces]),
                    bsp3d_node_index
                ))
                return True
        return False

    # Recurses through bsp3d nodes detecting and fixing phantom BSP
    def find_phantom_and_fix(bsp3d_node_index, parent_halfspaces):
        # Ignore leaves (flagged) and non-existent nodes (-1)
        if bsp3d_node_index & 0x80000000 != 0:
            return

        bsp3d_node = bsp3d_nodes[bsp3d_node_index]
        front_halfspaces = parent_halfspaces + [(bsp3d_node.plane, True, bsp3d_node_index)]
        back_halfspaces = parent_halfspaces + [(bsp3d_node.plane, False, bsp3d_node_index)]

        # Currently just checking for -1 back child and leaf front child, the
        # most common case. What a -1 front child looks like is unknown and how
        # to fix it (if it even needs fixing) is TBD with more research.
        if bsp3d_node.back_child == -1 and bsp3d_node.front_child & 0x80000000 != 0:
            if plane_unoccluded(bsp3d_node.plane, bsp3d_node.front_child, bsp3d_node_index, parent_halfspaces):
                if not report_only:
                    bsp3d_node.back_child = bsp3d_node.front_child

        find_phantom_and_fix(bsp3d_node.front_child, front_halfspaces)
        # We may have set the child indices to be the same, so don't need to fix twice
        if bsp3d_node.back_child != bsp3d_node.front_child:
            find_phantom_and_fix(bsp3d_node.back_child, back_halfspaces)

    find_phantom_and_fix(0, [])

    if not report_only:
        tag.serialize(backup=False, temp=False)

fix_bsp("./bloodgulch.scenario_structure_bsp", False)
