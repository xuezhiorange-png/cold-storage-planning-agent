<script setup lang="ts">
import { ElButton, ElCard, ElForm, ElFormItem, ElInput, ElInputNumber } from 'element-plus'

import { useProjectForm } from '../composables/useProjectForm'
import type { PlanningRunRequest } from '../../../api/contracts/planning'

const props = withDefaults(defineProps<{
  /** Optional submit callback. Receives the validated and mapped request. */
  onSubmit?: (request: PlanningRunRequest) => Promise<void>
  /** Optional reset callback. Called after form fields are reset. */
  onReset?: () => void
}>(), {
  onSubmit: undefined,
  onReset: undefined
})

const {
  designInputs,
  factoryOverview,
  submitting,
  submitError,
  validationErrors,
  submit,
  reset
} = useProjectForm(props.onSubmit)

function handleReset() {
  reset()
  props.onReset?.()
}

function fieldError(field: string): string {
  const err = validationErrors.value.find(e => e.field === field)
  return err?.message ?? ''
}
</script>

<template>
  <ElCard class="project-inputs-panel">
    <template #header>
      <div class="project-inputs-panel__header">
        <span>项目设计输入</span>
        <ElButton size="small" @click="handleReset">重置</ElButton>
      </div>
    </template>

    <ElForm label-position="top" class="project-inputs-panel__form">
      <!-- Factory Overview -->
      <h3 class="project-inputs-panel__section-title">工厂概况</h3>

      <ElFormItem label="工厂名称">
        <ElInput v-model="factoryOverview.factoryName" placeholder="输入工厂名称" />
      </ElFormItem>

      <ElFormItem
        label="种植面积（亩）"
        :error="fieldError('plantingAreaMu')"
      >
        <ElInputNumber
          v-model="factoryOverview.plantingAreaMu"
          :min="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="主要品种">
        <ElInput v-model="factoryOverview.mainVarieties" placeholder="输入主要品种" />
      </ElFormItem>

      <!-- Design Inputs -->
      <h3 class="project-inputs-panel__section-title">工艺参数</h3>

      <ElFormItem
        label="日入库量 (吨)"
        :error="fieldError('dailyInboundMassTons')"
      >
        <ElInputNumber
          v-model="designInputs.dailyInboundMassTons"
          :min="0.1"
          :step="1"
          :precision="1"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="每日工作时间 (小时)"
        :error="fieldError('workingHoursPerDay')"
      >
        <ElInputNumber
          v-model="designInputs.workingHoursPerDay"
          :min="1"
          :max="24"
          :step="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="成品库库存天数"
        :error="fieldError('finishedStorageDays')"
      >
        <ElInputNumber
          v-model="designInputs.finishedStorageDays"
          :min="0.5"
          :step="0.5"
          :precision="1"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="主要包材库存天数"
        :error="fieldError('packagingStorageDays')"
      >
        <ElInputNumber
          v-model="designInputs.packagingStorageDays"
          :min="1"
          :step="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="辅助包材库存天数"
        :error="fieldError('auxiliaryPackagingStorageDays')"
      >
        <ElInputNumber
          v-model="designInputs.auxiliaryPackagingStorageDays"
          :min="1"
          :step="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="预冷比例"
        :error="fieldError('precoolingRequiredRatio')"
      >
        <ElInputNumber
          v-model="designInputs.precoolingRequiredRatio"
          :min="0"
          :max="1"
          :step="0.05"
          :precision="2"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="原果暂存比例"
        :error="fieldError('rawStorageRatio')"
      >
        <ElInputNumber
          v-model="designInputs.rawStorageRatio"
          :min="0"
          :max="1"
          :step="0.05"
          :precision="2"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="一级预冷工作时间 (小时)"
        :error="fieldError('primaryPrecoolingWorkingHours')"
      >
        <ElInputNumber
          v-model="designInputs.primaryPrecoolingWorkingHours"
          :min="1"
          :max="24"
          :step="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="二级预冷工作时间 (小时)"
        :error="fieldError('secondaryPrecoolingWorkingHours')"
      >
        <ElInputNumber
          v-model="designInputs.secondaryPrecoolingWorkingHours"
          :min="1"
          :max="24"
          :step="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="成品托位重量 (kg)"
        :error="fieldError('finishedGoodsPalletWeightKg')"
      >
        <ElInputNumber
          v-model="designInputs.finishedGoodsPalletWeightKg"
          :min="50"
          :step="50"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="冻果比例"
        :error="fieldError('frozenFruitRatio')"
      >
        <ElInputNumber
          v-model="designInputs.frozenFruitRatio"
          :min="0"
          :max="1"
          :step="0.05"
          :precision="2"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="冻果库存天数"
        :error="fieldError('frozenStorageDays')"
      >
        <ElInputNumber
          v-model="designInputs.frozenStorageDays"
          :min="1"
          :step="1"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem
        label="冻果托位重量 (kg)"
        :error="fieldError('frozenGoodsPalletWeightKg')"
      >
        <ElInputNumber
          v-model="designInputs.frozenGoodsPalletWeightKg"
          :min="50"
          :step="50"
          :precision="0"
          controls-position="right"
          style="width: 100%"
        />
      </ElFormItem>

      <!-- Submit -->
      <ElFormItem>
        <ElButton
          type="primary"
          :loading="submitting"
          style="width: 100%"
          @click="submit"
        >
          {{ submitting ? '提交中...' : '运行规划' }}
        </ElButton>
      </ElFormItem>

      <div
        v-if="submitError"
        class="project-inputs-panel__error"
      >
        {{ submitError }}
      </div>
    </ElForm>
  </ElCard>
</template>

<style scoped>
.project-inputs-panel {
  max-width: 520px;
}

.project-inputs-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.project-inputs-panel__form {
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 4px;
}

.project-inputs-panel__section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #e4e7ed;
  padding-bottom: 6px;
}

.project-inputs-panel__error {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  background: #fef0f0;
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.4;
}
</style>
