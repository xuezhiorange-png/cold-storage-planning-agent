<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCard } from 'element-plus'

import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import {
  createProductionSchemeRunApi,
  type ProductionSchemeRunResponse
} from './productionSchemeRunApi'

const workbench = useWorkbenchContextStore()
const persisted = usePersistedPlanningResultsStore()
const api = createProductionSchemeRunApi()

const loading = ref(false)
const error = ref('')
const result = ref<ProductionSchemeRunResponse | null>(null)

const fiveStageReady = computed(() => persisted.fiveStageProgress.chainComplete)

async function runProductionScheme(): Promise<void> {
  if (!workbench.projectId || workbench.versionNumber === null) {
    error.value = '项目上下文未就绪'
    return
  }
  loading.value = true
  error.value = ''
  try {
    result.value = await api.createRun(workbench.projectId, workbench.versionNumber)
    await workbench.refreshWorkflow()
  } catch (err: unknown) {
    result.value = null
    error.value = err instanceof Error ? err.message : '生产方案评分请求失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (workbench.isReady) {
    void persisted.load()
    if (!workbench.workflow) {
      void workbench.refreshWorkflow()
    }
  }
})

watch(
  () => [workbench.projectId, workbench.versionNumber] as const,
  () => {
    void persisted.load()
  }
)
</script>

<template>
  <ElCard class="production-scheme-run-panel">
    <template #header>
      <div class="production-scheme-run-panel__header">
        <span>生产方案评分</span>
      </div>
    </template>

    <p class="production-scheme-run-panel__note">
      通过公共 API 持久化 <code>source_mode=production</code> 方案运行。界面仅展示后端返回的已持久化元数据，不在前端计算工程量。
    </p>

    <ElAlert
      v-if="!fiveStageReady"
      type="info"
      :closable="false"
      show-icon
      title="需先完成五阶段持久化"
      description="请先提交五阶段执行并确认规范五阶段结果已持久化。"
      class="production-scheme-run-panel__alert"
    />

    <div class="production-scheme-run-panel__actions">
      <ElButton
        type="primary"
        :loading="loading"
        :disabled="!workbench.isReady || !fiveStageReady"
        @click="runProductionScheme"
      >
        运行生产方案评分
      </ElButton>
    </div>

    <ElAlert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      :title="error"
      class="production-scheme-run-panel__alert"
    />

    <dl v-if="result" class="production-scheme-run-panel__meta">
      <div>
        <dt>运行 ID</dt>
        <dd>{{ result.run_id }}</dd>
      </div>
      <div>
        <dt>来源模式</dt>
        <dd>{{ result.source_mode }}</dd>
      </div>
      <div>
        <dt>来源绑定 ID</dt>
        <dd>{{ result.source_binding_id }}</dd>
      </div>
      <div>
        <dt>推荐方案代码</dt>
        <dd>{{ result.recommended_scheme_code ?? '—' }}</dd>
      </div>
      <div>
        <dt>需复核</dt>
        <dd>{{ result.requires_review ? '是' : '否' }}</dd>
      </div>
      <details class="production-scheme-run-panel__hashes">
        <summary>结果哈希</summary>
        <dl class="production-scheme-run-panel__hash-list">
          <div>
            <dt>combined_source_hash</dt>
            <dd class="production-scheme-run-panel__hash">{{ result.combined_source_hash }}</dd>
          </div>
          <div>
            <dt>content_hash</dt>
            <dd class="production-scheme-run-panel__hash">{{ result.content_hash }}</dd>
          </div>
        </dl>
      </details>
    </dl>
  </ElCard>
</template>

<style scoped>
.production-scheme-run-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.production-scheme-run-panel__note {
  margin: 0 0 12px;
  font-size: 13px;
  color: #5f7a99;
  line-height: 1.45;
}

.production-scheme-run-panel__alert {
  margin-bottom: 12px;
}

.production-scheme-run-panel__actions {
  margin-bottom: 12px;
}

.production-scheme-run-panel__meta {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 12px;
}

.production-scheme-run-panel__meta div {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 8px;
}

.production-scheme-run-panel__meta dt {
  margin: 0;
  color: #6b7a8f;
}

.production-scheme-run-panel__meta dd {
  margin: 0;
  word-break: break-all;
}

.production-scheme-run-panel__hashes {
  margin-top: 4px;
  font-size: 12px;
}

.production-scheme-run-panel__hashes summary {
  cursor: pointer;
  color: #40566f;
  font-weight: 600;
}

.production-scheme-run-panel__hash-list {
  display: grid;
  gap: 6px;
  margin: 8px 0 0;
}

.production-scheme-run-panel__hash-list div {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 8px;
}

.production-scheme-run-panel__hash-list dt {
  margin: 0;
  color: #6b7a8f;
}

.production-scheme-run-panel__hash-list dd {
  margin: 0;
  word-break: break-all;
}

.production-scheme-run-panel__hash {
  font-family: monospace;
  font-size: 11px;
}
</style>
