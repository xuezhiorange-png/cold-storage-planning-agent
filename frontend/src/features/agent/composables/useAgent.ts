import { ref } from 'vue'

export interface UseAgentReturn {
  isOpen: import('vue').Ref<boolean>
  availability: 'unavailable'
  toggle: () => void
  close: () => void
  setToggleRef: (el: HTMLElement | null) => void
}

/**
 * Composable for the AI agent chat panel.
 *
 * No agent backend exists — returns availability: 'unavailable' and provides
 * only UI state (open/close) for the drawer.
 */
export function useAgent(): UseAgentReturn {
  const isOpen = ref(false)

  let toggleButtonRef: HTMLElement | null = null

  function setToggleRef(el: HTMLElement | null): void {
    toggleButtonRef = el
  }

  function toggle(): void {
    isOpen.value = !isOpen.value
    if (!isOpen.value && toggleButtonRef) {
      setTimeout(() => toggleButtonRef?.focus(), 100)
    }
  }

  function close(): void {
    isOpen.value = false
    if (toggleButtonRef) {
      setTimeout(() => toggleButtonRef?.focus(), 100)
    }
  }

  return {
    isOpen,
    availability: 'unavailable',
    toggle,
    close,
    setToggleRef
  }
}
