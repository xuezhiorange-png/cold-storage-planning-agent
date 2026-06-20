"""Pure deterministic engineering calculators.

Core planning calculators (Task 4):
  - ``throughput`` — hourly throughput and labour requirements
  - ``inventory``  — base, safety, peak, and design inventory
  - ``pallets``    — pallet counts and positions
  - ``precooling`` — batch cycles, rooms, and capacity margins
  - ``areas``      — zone-by-zone area breakdown

Cooling load and equipment calculators (Task 5):
  - ``cooling_load`` — envelope, product, infiltration, internal, defrost loads
  - ``equipment``    — evaporator, compressor, condenser capability
  - ``power``        — installed electrical power (kW(e))

Legacy calculators:
  - ``CalculationService`` — throughput, inventory, storage capacity,
    precooling, room area, cooling load, equipment requirement
  - ``ColdRoomZonePlanner`` — cold room zone planning
  - ``InvestmentEstimator`` — investment estimation
"""
