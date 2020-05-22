# Halo BSP experiments
This repo contains a few scripts used to experiment with and visualize Halo's `scenario_structure_bsp` tag structure with the goal of reverse engineering game behaviour, documenting field purposes, and trying to solve the longstanding phantom BSP problem.

## torture.py
Alters BSP data in various ways to see how the game reacts.

## fix-phantom.py
Fixes the phantom BSP found in Danger Canyon's central ramps area.

## bsp-to-collada.py
Can be used (with some path edits) to convert a BSP tag's collision BSP tree to Collada format. The tree structure is retained with 2D BSPs and surfaces at the leaves, along with node planes when they are defined by level surfaces. The collada file can then be imported into Blender for troubleshooting:

![](bsp-debug.jpg)
