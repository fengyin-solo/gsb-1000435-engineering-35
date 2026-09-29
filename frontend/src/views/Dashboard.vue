<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">
          汇总各业务模块的关键指标，先看总量再看异常。
          数字按运单明细在同一事务内重算，统计参考日：{{ refDate || '—' }}。
        </p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>业务模块</th>
          <th>在册总量</th>
          <th>当日新增</th>
          <th>待处理</th>
          <th>异常量</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.label || row.name }}</td>
          <td>{{ row.total }}</td>
          <td>{{ row.has_date === false ? '—' : row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="loadError" class="page-desc">概览暂时不可用，显示为全 0 占位，请确认后端服务已启动。</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  ref_date: string
  cards: { label: string; value: number }[]
  modules: {
    name: string
    label?: string
    total: number
    created: number
    pending: number
    abnormal: number
    has_date?: boolean
  }[]
}

const EMPTY: Overview = {
  ref_date: '',
  cards: [
    { label: '业务模块', value: 0 },
    { label: '在册总量', value: 0 },
    { label: '当日新增', value: 0 },
    { label: '待处理', value: 0 },
    { label: '异常量', value: 0 },
  ],
  modules: [],
}

const cards = ref<Overview['cards']>(EMPTY.cards)
const moduleRows = ref<Overview['modules']>([])
const refDate = ref('')
const loadError = ref(false)

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    refDate.value = payload.ref_date
    loadError.value = false
  } catch {
    // 后端没起来时只做空态占位，不伪造任何业务数字
    cards.value = EMPTY.cards
    moduleRows.value = []
    loadError.value = true
  }
})
</script>
