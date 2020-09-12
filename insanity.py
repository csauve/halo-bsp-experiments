from reclaimer.hek.defs.sbsp import sbsp_def
from reclaimer.hek.defs.scnr import scnr_def
from struct import unpack, pack_into
from types import MethodType
import numpy as np
import argparse

def offset_point(point, offset):
    point.x += offset[0]
    point.y += offset[1]
    point.z += offset[2]

def offset_plane(plane, offset):
    offset = np.array([offset[0], offset[1], offset[2]])
    plane_normal = np.array([plane.i, plane.j, plane.k])
    offset_d = np.dot(plane_normal, offset)
    plane.d += offset_d

vert_unpacker = MethodType(unpack, "<3f")
vert_packer = MethodType(pack_into, "<3f")

def offset_level(bsp_path, scenario_path, offset):
    bsp_tag = sbsp_def.build(filepath=bsp_path)
    bsp = bsp_tag.data.tagdata
    scenario_tag = scnr_def.build(filepath=scenario_path)
    scenario = scenario_tag.data.tagdata

    for collision_bsp in bsp.collision_bsp.STEPTREE:
        for plane in collision_bsp.planes.STEPTREE:
            offset_plane(plane, offset)
        for vert in collision_bsp.vertices.STEPTREE:
            offset_point(vert, offset)

    for lightmap in bsp.lightmaps.STEPTREE:
        for material in lightmap.materials.STEPTREE:
            # material planes not included because zero length normals
            offset_point(material.centroid, offset)
            vert_count = material.vertices_count
            vert_buffer = material.uncompressed_vertices.STEPTREE
            for i in range(vert_count):
                vert_offset = i * 56
                x, y, z = vert_unpacker(vert_buffer[vert_offset: vert_offset + 12])
                vert_packer(vert_buffer, vert_offset, x + offset[0], y + offset[1], z + offset[2])

    for flare_marker in bsp.lens_flare_markers.STEPTREE:
        offset_point(flare_marker.position, offset)

    for cluster in bsp.clusters.STEPTREE:
        for subcluster in cluster.subclusters.STEPTREE:
            subcluster.world_bounds_x[0] += offset[0]
            subcluster.world_bounds_x[1] += offset[0]
            subcluster.world_bounds_y[0] += offset[1]
            subcluster.world_bounds_y[1] += offset[1]
            subcluster.world_bounds_z[0] += offset[2]
            subcluster.world_bounds_z[1] += offset[2]
        for mirror in cluster.mirrors.STEPTREE:
            offset_plane(mirror.plane, offset)
            for vert in mirror.vertices.STEPTREE:
                offset_point(vert, offset)

    for cluster_portal in bsp.cluster_portals.STEPTREE:
        offset_point(cluster_portal.centroid, offset)
        for vert in cluster_portal.vertices.STEPTREE:
            offset_point(vert, offset)

    for surface in bsp.breakable_surfaces.STEPTREE:
        offset_point(surface.centroid, offset)

    for fog_plane in bsp.fog_planes.STEPTREE:
        offset_plane(fog_plane.plane, offset)
        for vert in fog_plane.vertices.STEPTREE:
            offset_point(vert, offset)

    for weather_polyhedra in bsp.weather_polyhedras.STEPTREE:
        offset_point(weather_polyhedra.bounding_sphere_center, offset)
        for plane in weather_polyhedra.planes.STEPTREE:
            offset_plane(plane, offset)

    for marker in bsp.markers.STEPTREE:
        offset_point(marker.position, offset)

    for decal in bsp.runtime_decals.STEPTREE:
        offset_point(decal.position, offset)

    for leaf_map_portal in bsp.leaf_map_portals.STEPTREE:
        for vert in leaf_map_portal.vertices.STEPTREE:
            offset_point(vert, offset)

    bsp.world_bounds_x[0] += offset[0]
    bsp.world_bounds_x[1] += offset[0]
    bsp.world_bounds_y[0] += offset[1]
    bsp.world_bounds_y[1] += offset[1]
    bsp.world_bounds_z[0] += offset[2]
    bsp.world_bounds_z[1] += offset[2]
    bsp.vehicle_floor += offset[2]
    bsp.vehicle_ceiling += offset[2]

    for player_spawn in scenario.player_starting_locations.STEPTREE:
        offset_point(player_spawn.position, offset)

    bsp_tag.serialize(backup=False, temp=False)
    scenario_tag.serialize(backup=False, temp=False)


parser = argparse.ArgumentParser()
parser.add_argument("bsp", help="Path to the BSP file to modify")
parser.add_argument("scenario", help="Path to the scenario file to modify")
parser.add_argument("x", type=float, help="X offset")
parser.add_argument("y", type=float, help="Y offset")
parser.add_argument("z", type=float, help="Z (vertical) offset")
args = parser.parse_args()
offset_level(args.bsp, args.scenario, (args.x, args.y, args.z))
