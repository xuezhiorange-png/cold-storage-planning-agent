import { ref } from 'vue'

export interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export interface UseAgentReturn {
  isOpen: Ref<boolean>
  messages: Ref<AgentMessage[]>
  loading: Ref<boolean>
  inputText: Ref<string>
  toggle: () => void
  send: () => Promise<void>
  clear: () => void
}

type Ref<T> = import('vue').Ref<T>

/**
 * Composable for the AI agent chat panel.
 *
 * Manages open/close state, message history, and sending messages
 * to the agent backend endpoint.
 */
export function useAgent(): UseAgentReturn {
  const isOpen = ref(false)
  const messages = ref<AgentMessage[]>([])
  const loading = ref(false)
  const inputText = ref('')

  function toggle(): void {
    isOpen.value = !isOpen.value
    if (!isOpen.value) {
      // Reset input on close
      inputText.value = ''
    }
  }

  async function send(): Promise<void> {
    const text = inputText.value.trim()
    if (!text) return

    const userMessage: AgentMessage = {
      role: 'user',
      content: text,
      timestamp: Date.now()
    }
    messages.value.push(userMessage)
    inputText.value = ''
    loading.value = true

    try {
      const res = await fetch('/api/v1/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: messages.value.slice(-20)
        })
      })

      if (!res.ok) {
        messages.value.push({
          role: 'assistant',
          content: '抱歉，请求失败，请稍后重试。',
          timestamp: Date.now()
        })
        return
      }

      const data = await res.json()
      messages.value.push({
        role: 'assistant',
        content: data.reply ?? data.message ?? '(无回复)',
        timestamp: Date.now()
      })
    } catch {
      messages.value.push({
        role: 'assistant',
        content: '网络错误，请检查后端服务。',
        timestamp: Date.now()
      })
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    messages.value = []
    inputText.value = ''
  }

  return {
    isOpen,
    messages,
    loading,
    inputText,
    toggle,
    send,
    clear
  }
}
