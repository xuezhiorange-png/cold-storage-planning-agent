export type ParameterState = 'confirmed' | 'calculated' | 'default' | 'tentative' | 'review' | 'invalid' | 'missing'

export interface DesignParameter {
  key: string
  label: string
  value: string
  unit: string
  state: ParameterState
}
