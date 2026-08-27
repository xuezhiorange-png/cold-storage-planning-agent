<script setup lang="ts">
import { computed } from 'vue'
import { ElAlert, ElCard, ElForm } from 'element-plus'

import BundleLeafField from './BundleLeafField.vue'
import type { FiveStageFieldError } from '../../../stores/fiveStageExecution'
import type { EngineeringInputFormState } from '../model/engineeringInputForm'

const props = defineProps<{
  modelValue: EngineeringInputFormState
  fieldError?: FiveStageFieldError | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: EngineeringInputFormState]
}>()

const form = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

function matchesFieldError(formKey: string): FiveStageFieldError | null {
  if (!props.fieldError?.formKey) return null
  return props.fieldError.formKey === formKey ? props.fieldError : null
}

function fieldErrorFor(formKey: string): { errorCode: string | null; errorMessage: string | null } {
  const match = matchesFieldError(formKey)
  return {
    errorCode: match?.code ?? null,
    errorMessage: match?.message ?? null
  }
}

function updateZonePlanning<K extends keyof EngineeringInputFormState['zonePlanning']>(
  key: K,
  value: EngineeringInputFormState['zonePlanning'][K]
): void {
  form.value = {
    ...form.value,
    zonePlanning: { ...form.value.zonePlanning, [key]: value }
  }
}

const unmappedFieldError = computed(() => {
  if (!props.fieldError) return null
  if (props.fieldError.formKey) return null
  return props.fieldError
})
</script>

<template>
  <div class="engineering-input-bundle-form">
    <ElAlert
      v-if="unmappedFieldError"
      type="error"
      :closable="false"
      show-icon
      :title="`[${unmappedFieldError.code}] ${unmappedFieldError.message}`"
      :description="`字段路径: ${unmappedFieldError.fieldPath}`"
      class="engineering-input-bundle-form__alert"
    />

    <ElForm label-position="top">
      <ElCard shadow="never" class="engineering-input-bundle-form__section">
        <template #header>过程规划输入 (zone_planning_inputs)</template>
        <BundleLeafField
          label="日入库量"
          field-key="zonePlanning.dailyInboundMassKg"
          :model-value="form.zonePlanning.dailyInboundMassKg"
          unit="kg/day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.dailyInboundMassKg')"
          @update:model-value="updateZonePlanning('dailyInboundMassKg', $event as number | null)"
        />
        <BundleLeafField
          label="成品储存天数"
          field-key="zonePlanning.finishedStorageDays"
          :model-value="form.zonePlanning.finishedStorageDays"
          unit="day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.finishedStorageDays')"
          @update:model-value="updateZonePlanning('finishedStorageDays', $event as number | null)"
        />
        <BundleLeafField
          label="冻果储存天数"
          field-key="zonePlanning.frozenStorageDays"
          :model-value="form.zonePlanning.frozenStorageDays"
          unit="day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.frozenStorageDays')"
          @update:model-value="updateZonePlanning('frozenStorageDays', $event as number | null)"
        />
        <BundleLeafField
          label="主包材储存天数"
          field-key="zonePlanning.mainPackagingStorageDays"
          :model-value="form.zonePlanning.mainPackagingStorageDays"
          unit="day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.mainPackagingStorageDays')"
          @update:model-value="updateZonePlanning('mainPackagingStorageDays', $event as number | null)"
        />
        <BundleLeafField
          label="辅包材储存天数"
          field-key="zonePlanning.auxiliaryPackagingStorageDays"
          :model-value="form.zonePlanning.auxiliaryPackagingStorageDays"
          unit="day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.auxiliaryPackagingStorageDays')"
          @update:model-value="updateZonePlanning('auxiliaryPackagingStorageDays', $event as number | null)"
        />
      </ElCard>
    </ElForm>
  </div>
</template>

<style scoped>
.engineering-input-bundle-form {
  display: grid;
  gap: 16px;
}

.engineering-input-bundle-form__section {
  margin-bottom: 8px;
}

.engineering-input-bundle-form__alert {
  margin-bottom: 8px;
}
</style>
