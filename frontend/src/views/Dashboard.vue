<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">
          指标按原始业务记录实时汇总（口径：{{ sourceText }}），与各模块明细同源。
        </p>
      </div>
      <div v-if="snapshotAt" class="page-desc">快照时间：{{ snapshotAt }}</div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>记录总数</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.label }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type ModuleRow = {
  name: string
  label: string
  created: number
  pending: number
  abnormal: number
}

type Overview = {
  cards: { label: string; value: number }[]
  modules: ModuleRow[]
  source?: string
  snapshot_at?: string | null
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<ModuleRow[]>([])
const sourceText = ref('运行数据')
const snapshotAt = ref<string | null>(null)

const EMPTY: Overview = {
  cards: [
    { label: '业务模块', value: 0 },
    { label: '记录总数', value: 0 },
    { label: '待处理', value: 0 },
    { label: '异常量', value: 0 },
  ],
  modules: [
    { name: 'shipment', label: '发运单管理', created: 0, pending: 0, abnormal: 0 },
    { name: 'temp_monitor', label: '温控监测', created: 0, pending: 0, abnormal: 0 },
    { name: 'vehicle', label: '车辆调度', created: 0, pending: 0, abnormal: 0 },
    { name: 'driver', label: '司机管理', created: 0, pending: 0, abnormal: 0 },
    { name: 'cold_storage', label: '冷库运营', created: 0, pending: 0, abnormal: 0 },
    { name: 'loading', label: '装卸作业', created: 0, pending: 0, abnormal: 0 },
    { name: 'alert', label: '报警管理', created: 0, pending: 0, abnormal: 0 },
    { name: 'route', label: '线路规划', created: 0, pending: 0, abnormal: 0 },
    { name: 'reefer_unit', label: '制冷机组', created: 0, pending: 0, abnormal: 0 },
    { name: 'fuel', label: '油料管理', created: 0, pending: 0, abnormal: 0 },
    { name: 'delivery', label: '签收回单', created: 0, pending: 0, abnormal: 0 },
    { name: 'break_chain', label: '断链追溯', created: 0, pending: 0, abnormal: 0 },
    { name: 'dock', label: '月台管理', created: 0, pending: 0, abnormal: 0 },
    { name: 'package', label: '包装管理', created: 0, pending: 0, abnormal: 0 },
    { name: 'toll', label: '通行费用', created: 0, pending: 0, abnormal: 0 },
    { name: 'sanitation', label: '车辆消杀', created: 0, pending: 0, abnormal: 0 },
    { name: 'contract', label: '承运合同', created: 0, pending: 0, abnormal: 0 },
    { name: 'insurance', label: '货运保险', created: 0, pending: 0, abnormal: 0 },
  ],
  source: 'runtime',
  snapshot_at: null,
}

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    sourceText.value = payload.source === 'snapshot' ? '概览快照' : '运行数据（实时）'
    snapshotAt.value = payload.snapshot_at ?? null
  } catch {
    cards.value = EMPTY.cards
    moduleRows.value = EMPTY.modules
    sourceText.value = '接口不可用，显示空看板'
  }
})
</script>
