from reclaimer.hek.defs.sbsp import sbsp_def

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

    # Determines if the plane is not obstructed by the surfaces under this node
    def plane_exposed(plane_index, bsp3d_node_index):
        # meaning of flagged plane index is unknown...
        if plane_index & 0x80000000:
            plane_index = plane_index & 0x7FFFFFFF
            print("Converted flagged plane index to " + str(plane_index))
        # first we need the set of all surface indices under this node
        surface_indices = gather_bsp3d_node_surfaces(bsp3d_node_index)

        # Next, identify which surface was used to define the 3d node's plane
        plane_surface_index = None
        for s in surface_indices:
            surface = surfaces[s]
            if surface.plane & 0x7FFFFFFF == plane_index:
                plane_surface_index = s

        if plane_surface_index is None:
            return False

        #TODO
        # Get the bounding edges of the extended surface which was used for the plane

        # For each bounding edge, determine if it intersects the convex polyhedron
        # defined by this node's parents' planes. Also need to consider edges with
        # verts on the boundary.

        return False

    # Recurses through bsp3d nodes detecting and fixing phantom BSP
    def fix_node(bsp3d_node_index):
        # Ignore leaves (flagged) and non-existent nodes (-1)
        if bsp3d_node_index & 0x80000000 != 0:
            return

        bsp3d_node = bsp3d_nodes[bsp3d_node_index]

        # Currently just checking for -1 back child, since what a -1 front child
        # looks like is unknown and how to fix it is TBD.
        if bsp3d_node.back_child == -1 and plane_exposed(bsp3d_node.plane, bsp3d_node.front_child):
            # this is the most common case of -1 index -- no surfaces behind a plane
            print("Phantom BSP detected in bsp3d_node " + str(bsp3d_node_index))
            if not report_only:
                bsp3d_node.back_child = bsp3d_node.front_child

        fix_node(bsp3d_node.front_child)
        # We may have set the child indices to be the same, so don't need to fix twice
        if bsp3d_node.back_child != bsp3d_node.front_child:
            fix_node(bsp3d_node.back_child)

    fix_node(0)
    if not report_only:
        tag.serialize(backup=False, temp=False)

fix_bsp("./dangercanyon.scenario_structure_bsp", True)
