<script setup lang="ts">
import { computed } from 'vue'
import { ElFormItem, ElInput, ElInputNumber } from 'element-plus'

const props = defineProps<{
  label: string
  fieldKey: string
  modelValue: string | number | null
  unit?: string
  type?: 'text' | 'number'
  precision?: number
  errorCode?: string | null
  errorMessage?: string | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string | number | null]
}>()

const displayError = computed(() => {
  if (!props.errorMessage) return ''
  if (props.errorCode) {
    return `[${props.errorCode}] ${props.errorMessage}`
  }
  return props.errorMessage
})

function onNumberChange(value: number | undefined): void {
  emit('update:modelValue', value ?? null)
}
</script>

<template>
  <ElFormItem
    :label="unit ? `${label} (${unit})` : label"
    :error="displayError"
    :data-field-key="fieldKey"
  >
    <ElInputNumber
      v-if="type === 'number'"
      :model-value="typeof modelValue === 'number' ? modelValue : undefined"
      :precision="precision ?? 2"
      :disabled="disabled"
      controls-position="right"
      style="width: 100%"
      @update:model-value="onNumberChange"
    />
    <ElInput
      v-else
      :model-value="modelValue === null ? '' : String(modelValue)"
      :disabled="disabled"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </ElFormItem>
</template>
