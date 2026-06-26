<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

import AgentPanel from '../features/agent/components/AgentPanel.vue'
</script>

<template>
  <div class="application-shell">
    <header class="application-shell__header">
      <div>
        <strong>冷库规划工作台</strong>
        <span>Cold Storage Planning Workbench</span>
      </div>
      <nav aria-label="应用导航">
        <RouterLink to="/workbench/project">规划工作台</RouterLink>
      </nav>
      <AgentPanel />
    </header>

    <main class="application-shell__content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.application-shell {
  min-height: 100vh;
}

.application-shell__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 52px;
  padding: 8px 16px;
  border-bottom: 1px solid #123a63;
  color: #fff;
  background: #071a31;
}

.application-shell__header > div {
  display: grid;
  gap: 2px;
}

.application-shell__header strong {
  font-size: 16px;
}

.application-shell__header span {
  font-size: 11px;
  color: #b8cae0;
}

.application-shell__header nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.application-shell__header a {
  border-radius: 6px;
  padding: 7px 10px;
  color: #dbe8f6;
  text-decoration: none;
}

.application-shell__header a.router-link-active {
  color: #fff;
  background: #123a63;
}

.application-shell__content {
  min-width: 0;
}

@media (max-width: 640px) {
  .application-shell__header span {
    display: none;
  }
}
</style>
