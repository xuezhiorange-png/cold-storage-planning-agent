# Scheme Generation Specification

## Overview

The scheme generation module produces deterministic cold-room scheme candidates from Task 4/5 calculation results.

## Profiles

### balanced
- One room per zone from Task 4 zone planning
- Preserves all area, position, and capacity values
- No merging or splitting

### consolidated_large_rooms
- Merges zones with same temperature_level, compatible process_compatibility, same hygiene_zone
- Cannot merge raw + finished
- Cannot merge different temperature levels
- Reduces room count, doors, and partitions
- Capacity and positions preserved
- Requires review when total layout info is missing

### segmented_small_rooms
- Splits zones exceeding max_positions_per_room or max_area_per_room_m2
- Split ratio is uniform across parts
- Total capacity and positions preserved
- Increases room count, doors, and partitions
- Improves failure isolation

## Input Sources

All engineering quantities come from Task 4/5 snapshots:
- Zone results (area, positions, capacity, temperature, process, hygiene)
- Investment result
- Cooling load result (kW(r))
- Equipment result (kW(r), kW(e))

The scheme module does NOT recalculate:
- Inventory quantities
- Pallet counts
- Precooling capacity
- Zone areas
- Cooling loads
- Compressor capacity
- Condenser heat rejection
- Installed power
