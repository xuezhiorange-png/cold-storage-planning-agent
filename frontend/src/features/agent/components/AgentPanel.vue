<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

import { useAgent } from '../composables/useAgent'

const { isOpen, availability, toggle, close, setToggleRef } = useAgent()

const drawerRef = ref<HTMLElement | null>(null)
const closeButtonRef = ref<HTMLButtonElement | null>(null)

/* ── Focus management via MutationObserver ─────────
   Uses a MutationObserver to detect when the close button
   is added to the DOM by Teleport, then focuses it.
   This is more reliable than Vue reactivity (watch/watchEffect)
   across different jsdom versions and Node runtimes. */

let focusObserver: MutationObserver | null = null

function setupFocusObserver(): void {
  if (typeof document === 'undefined') return
  focusObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of Array.from(mutation.addedNodes)) {
        if (!(node instanceof HTMLElement)) continue
        const btn =
          node.matches?.('.agent-panel__close-btn')
            ? node
            : node.querySelector?.('.agent-panel__close-btn')
        if (btn instanceof HTMLButtonElement) {
          closeButtonRef.value = btn
          btn.focus()
          return
        }
      }
    }
  })
  focusObserver.observe(document.body, { childList: true, subtree: true })
}

onMounted(setupFocusObserver)

onUnmounted(() => {
  focusObserver?.disconnect()
  focusObserver = null
})

/* ── Keyboard / focus trap ───────────────────────── */

function getFocusableElements(): HTMLElement[] {
  if (!drawerRef.value) return []
  return Array.from(
    drawerRef.value.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
  )
}

function onDrawerKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = getFocusableElements()
  if (focusable.length === 0) {
    event.preventDefault()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const currentIdx = focusable.indexOf(document.activeElement as HTMLElement)

  if (event.shiftKey) {
    if (currentIdx <= 0 || document.activeElement === drawerRef.value) {
      event.preventDefault()
      last.focus()
    }
  } else {
    if (currentIdx === focusable.length - 1 || currentIdx < 0) {
      event.preventDefault()
      first.focus()
    }
  }
}
</script>

<template>
  <div class="agent-panel">
    <!-- Toggle button -->
    <button
      :ref="(el) => setToggleRef(el as HTMLElement | null)"
      class="agent-panel__toggle"
      type="button"
      :class="{
        'agent-panel__toggle--active': isOpen,
        'agent-panel__toggle--unavailable': availability === 'unavailable'
      }"
      :aria-label="availability === 'unavailable' ? '查看 AI 助手不可用说明' : '切换AI助手'"
      @click="toggle"
    >
      AI
    </button>

    <!-- Chat overlay -->
    <Teleport to="body">
      <Transition name="agent-slide">
        <div v-if="isOpen" class="agent-panel__overlay" @click.self="close">
          <aside
            ref="drawerRef"
            class="agent-panel__drawer"
            role="dialog"
            aria-modal="true"
            aria-label="AI 助手"
            tabindex="-1"
            @click.stop
            @keydown="onDrawerKeydown"
          >
            <header class="agent-panel__header">
              <strong
                :class="{ 'agent-panel__header--disabled': availability === 'unavailable' }"
              >AI 助手</strong>
              <div class="agent-panel__header-actions">
                <button
                  ref="closeButtonRef"
                  type="button"
                  class="agent-panel__close-btn"
                  aria-label="关闭"
                  @click="close"
                >
                  ✕
                </button>
              </div>
            </header>

            <!-- Unavailable banner -->
            <div class="agent-panel__unavailable" role="status" aria-live="polite">
              <p>AI 助手当前不可用</p>
              <p>后端尚未部署 Agent 服务。</p>
              <p>当前无法发送消息或执行工具操作。</p>
            </div>
          </aside>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* ── Toggle button ────────────────────────────────── */
.agent-panel__toggle {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid #5b7fa4;
  border-radius: 50%;
  color: #fff;
  background: #123a63;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  transition: background 0.15s;
}

.agent-panel__toggle:hover,
.agent-panel__toggle--active {
  background: #0b2a4a;
}

.agent-panel__toggle--unavailable {
  border-color: #9ca3af;
  background: #6b7280;
  opacity: 0.6;
}

/* ── Overlay ──────────────────────────────────────── */
.agent-panel__overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
  background: rgba(0, 0, 0, 0.25);
}

/* ── Drawer ───────────────────────────────────────── */
.agent-panel__drawer {
  display: grid;
  grid-template-rows: auto 1fr;
  width: min(400px, 100vw);
  height: 100%;
  background: #fff;
  box-shadow: -4px 0 24px rgba(11, 31, 58, 0.18);
  outline: none;
}

/* ── Header ───────────────────────────────────────── */
.agent-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #e0e6ed;
  background: #0b1f3a;
  color: #fff;
}

.agent-panel__header strong {
  font-size: 15px;
}

.agent-panel__header--disabled {
  opacity: 0.5;
}

.agent-panel__header-actions {
  display: flex;
  gap: 8px;
}

.agent-panel__close-btn {
  padding: 2px 8px;
  border: none;
  background: transparent;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
}

/* ── Unavailable banner ────────────────────────────── */
.agent-panel__unavailable {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  color: #6b7280;
  font-size: 14px;
  text-align: center;
  line-height: 1.6;
}

.agent-panel__unavailable p {
  margin: 0;
}

/* ── Transition ───────────────────────────────────── */
.agent-slide-enter-active,
.agent-slide-leave-active {
  transition: opacity 0.2s ease;
}

.agent-slide-enter-active .agent-panel__drawer,
.agent-slide-leave-active .agent-panel__drawer {
  transition: transform 0.2s ease;
}

.agent-slide-enter-from,
.agent-slide-leave-to {
  opacity: 0;
}

.agent-slide-enter-from .agent-panel__drawer,
.agent-slide-leave-to .agent-panel__drawer {
  transform: translateX(100%);
}
</style>
