<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

interface NavItem {
  path: string
  label: string
}

const navItems: NavItem[] = [
  { path: '/workbench/project', label: '基本信息' },
  { path: '/workbench/calculations', label: '计算结果' },
  { path: '/workbench/schemes', label: '方案比选' },
  { path: '/workbench/investment', label: '投资估算' },
  { path: '/workbench/power', label: '用电配置' },
  { path: '/workbench/reports', label: '报告输出' }
]
</script>

<template>
  <main class="workbench-layout">
    <nav class="workbench-layout__nav" aria-label="主流程导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="workbench-layout__nav-link"
        active-class="workbench-layout__nav-link--active"
        exact-active-class="workbench-layout__nav-link--active"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
    <section class="workbench-layout__content">
      <RouterView />
    </section>
  </main>
</template>

<style scoped>
.workbench-layout {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 0;
  min-height: calc(100vh - 52px);
}

/* ── Nav bar ─────────────────────────────────────── */
.workbench-layout__nav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: center;
  padding: 10px 16px;
  background: #f3f7fb;
  border-bottom: 1px solid #c7d4e3;
}

.workbench-layout__nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 6px 14px;
  border: 1px solid #c7d4e3;
  border-radius: 6px;
  background: #fff;
  color: #163f68;
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.workbench-layout__nav-link:hover {
  background: #ebf0f6;
  border-color: #8aa8c4;
}

.workbench-layout__nav-link--active {
  background: #123a63;
  border-color: #123a63;
  color: #fff;
}

/* ── Content area ─────────────────────────────────── */
.workbench-layout__content {
  padding: 16px;
  overflow-x: auto;
  min-width: 0;
}
</style>
