import v09Manifest from '@v09-operator-demo'

export const OPERATOR_DEMO_MANIFEST_SOURCE = 'samples/v09-process-input/manifest.json'

const zoneInputs = v09Manifest.operator_process_input.zone_planning_inputs

export function operatorDemoZoneLeaf(field: string): {
  value: string
  unit: string
  state: string
} {
  const leaf = zoneInputs[field]
  if (leaf == null) {
    throw new Error(`missing operator demo leaf ${field}`)
  }
  return leaf
}

export function operatorDemoZoneNumeric(field: string): number {
  return Number(operatorDemoZoneLeaf(field).value)
}

export function operatorDemoZoneValue(field: string): string {
  return operatorDemoZoneLeaf(field).value
}
