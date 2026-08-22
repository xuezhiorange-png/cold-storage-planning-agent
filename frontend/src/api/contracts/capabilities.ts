export interface CapabilityProjectionEntry {
  name: string
  status: string
  code?: string | null
  blocking?: boolean
  capability_state: string
  route_exposure?: string
}

export type AgentAvailabilityState = 'available' | 'not_ready' | 'unavailable'

export function resolveAgentAvailability(
  capabilities: CapabilityProjectionEntry[]
): AgentAvailabilityState {
  const agent = capabilities.find((entry) => entry.name === 'model_backed_agent')
  if (!agent) {
    return 'unavailable'
  }
  if (agent.status === 'available') {
    return 'available'
  }
  if (agent.status === 'not_ready' || agent.capability_state === 'AGENT_CAPABILITY_ENABLED_NOT_READY') {
    return 'not_ready'
  }
  return 'unavailable'
}
