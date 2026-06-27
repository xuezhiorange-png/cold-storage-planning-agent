import { ref, onUnmounted } from 'vue'

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
      // Only restore focus if drawer is closed
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
      // Opening — cancel any pending restore from previous close
      cancelPendingFocusRestore()
    } else {
      // Closing — schedule focus restore
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
    availability: 'unavailable',
    toggle,
    close,
    setToggleRef
  }
}
