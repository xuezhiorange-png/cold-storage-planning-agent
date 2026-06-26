<script setup lang="ts">
import { ElButton, ElInput } from 'element-plus'

import { useAgent } from '../composables/useAgent'

const { isOpen, messages, loading, inputText, toggle, send, clear } = useAgent()

function onKeydown(event: Event): void {
  const ke = event as KeyboardEvent
  if (ke.key === 'Enter' && !ke.shiftKey) {
    ke.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="agent-panel">
    <!-- Toggle button -->
    <button
      class="agent-panel__toggle"
      type="button"
      :class="{ 'agent-panel__toggle--active': isOpen }"
      aria-label="切换AI助手"
      @click="toggle"
    >
      AI
    </button>

    <!-- Chat overlay -->
    <Teleport to="body">
      <Transition name="agent-slide">
        <div v-if="isOpen" class="agent-panel__overlay" @click.self="toggle">
          <aside class="agent-panel__drawer" @click.stop>
            <header class="agent-panel__header">
              <strong>AI 助手</strong>
              <div class="agent-panel__header-actions">
                <button
                  type="button"
                  class="agent-panel__clear-btn"
                  aria-label="清除对话"
                  @click="clear"
                >清除</button>
                <button
                  type="button"
                  class="agent-panel__close-btn"
                  aria-label="关闭"
                  @click="toggle"
                >✕</button>
              </div>
            </header>

            <!-- Messages -->
            <div class="agent-panel__messages">
              <div
                v-for="(msg, idx) in messages"
                :key="idx"
                class="agent-panel__message"
                :class="`agent-panel__message--${msg.role}`"
              >
                <div class="agent-panel__bubble">
                  {{ msg.content }}
                </div>
              </div>

              <div v-if="loading" class="agent-panel__message agent-panel__message--assistant">
                <div class="agent-panel__bubble agent-panel__bubble--loading">
                  思考中...
                </div>
              </div>

              <div
                v-if="messages.length === 0 && !loading"
                class="agent-panel__empty"
              >
                我可以提取需求、生成参数变更建议、调用确定性计算工具并解释结果。
              </div>
            </div>

            <!-- Input -->
            <footer class="agent-panel__footer">
              <ElInput
                v-model="inputText"
                type="textarea"
                :rows="2"
                placeholder="输入自然语言需求，例如：日入库量调整为30吨"
                :disabled="loading"
                @keydown="onKeydown"
              />
              <ElButton
                type="primary"
                :disabled="!inputText.trim() || loading"
                :loading="loading"
                @click="send"
              >
                {{ loading ? '发送中...' : '发送' }}
              </ElButton>
            </footer>
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
  grid-template-rows: auto 1fr auto;
  width: min(400px, 100vw);
  height: 100%;
  background: #fff;
  box-shadow: -4px 0 24px rgba(11, 31, 58, 0.18);
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

.agent-panel__header-actions {
  display: flex;
  gap: 8px;
}

.agent-panel__clear-btn {
  padding: 2px 8px;
  border: 1px solid #5b7fa4;
  border-radius: 4px;
  background: transparent;
  color: #b8cae0;
  font-size: 12px;
  cursor: pointer;
}

.agent-panel__close-btn {
  padding: 2px 8px;
  border: none;
  background: transparent;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
}

/* ── Messages ─────────────────────────────────────── */
.agent-panel__messages {
  overflow-y: auto;
  padding: 12px 16px;
  display: grid;
  gap: 10px;
  align-content: start;
}

.agent-panel__message {
  display: flex;
}

.agent-panel__message--user {
  justify-content: flex-end;
}

.agent-panel__message--assistant {
  justify-content: flex-start;
}

.agent-panel__bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

.agent-panel__message--user .agent-panel__bubble {
  background: #123a63;
  color: #fff;
  border-bottom-right-radius: 2px;
}

.agent-panel__message--assistant .agent-panel__bubble {
  background: #f0f4f8;
  color: #0f1f33;
  border-bottom-left-radius: 2px;
}

.agent-panel__bubble--loading {
  color: #5d6f84;
  font-style: italic;
}

.agent-panel__empty {
  padding: 32px 16px;
  text-align: center;
  color: #6b7a8f;
  font-size: 13px;
  line-height: 1.5;
}

/* ── Footer ───────────────────────────────────────── */
.agent-panel__footer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px 16px;
  border-top: 1px solid #e0e6ed;
  background: #f8f9fb;
}

.agent-panel__footer .el-button {
  flex-shrink: 0;
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
