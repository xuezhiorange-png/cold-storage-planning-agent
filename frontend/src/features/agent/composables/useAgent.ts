import { computed, onUnmounted, ref } from 'vue'

import { resolveAgentAvailability } from '../../../api/contracts/capabilities'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

export type AgentAvailability = 'available' | 'not_ready' | 'unavailable'

export interface UseAgentReturn {
  isOpen: import('vue').Ref<boolean>
  availability: import('vue').ComputedRef<AgentAvailability>
  capabilityState: import('vue').ComputedRef<string>
  toggle: () => void
  close: () => void
  setToggleRef: (el: HTMLElement | null) => void
}

/**
 * Agent panel UI state. Availability follows backend capability projection;
 * optional assistance must not block the core workflow.
 */
export function useAgent(): UseAgentReturn {
  const workbench = useWorkbenchContextStore()
  const isOpen = ref(false)

  const availability = computed<AgentAvailability>(() => {
    const fromWorkflow = workbench.agentAssistance
    if (fromWorkflow) {
      if (fromWorkflow.available) return 'available'
      if (fromWorkflow.status === 'NOT_READY') return 'not_ready'
      return 'unavailable'
    }
    return resolveAgentAvailability(workbench.capabilities)
  })

  const capabilityState = computed(() => {
    if (workbench.agentAssistance?.capability_state) {
      return workbench.agentAssistance.capability_state
    }
    const agent = workbench.capabilities.find((entry) => entry.name === 'model_backed_agent')
    return agent?.capability_state ?? 'AGENT_CAPABILITY_DISABLED'
  })

  let toggleButtonRef: HTMLElement | null = null
  let focusRestoreTimer: ReturnType<typeof setTimeout> | null = null

  function cancelPendingFocusRestore(): void {
    if (focusRestoreTimer !== null) {
      clearTimeout(focusRestoreTimer)
      focusRestoreTimer = null
    }
  }

  function scheduleFocusRestore(): void {
    cancelPendingFocusRestore()
    focusRestoreTimer = setTimeout(() => {
      focusRestoreTimer = null
      if (!isOpen.value && toggleButtonRef) {
        toggleButtonRef.focus()
      }
    }, 100)
  }

  function setToggleRef(el: HTMLElement | null): void {
    toggleButtonRef = el
  }

  function toggle(): void {
    const willBeOpen = !isOpen.value
    isOpen.value = willBeOpen

    if (willBeOpen) {
      cancelPendingFocusRestore()
    } else {
      scheduleFocusRestore()
    }
  }

  function close(): void {
    isOpen.value = false
    scheduleFocusRestore()
  }

  onUnmounted(() => {
    cancelPendingFocusRestore()
  })

  return {
    isOpen,
    availability,
    capabilityState,
    toggle,
    close,
    setToggleRef
  }
}
