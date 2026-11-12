<template>
  <section class="page" data-module="query">
    <header class="page-head">
      <div>
        <h2>交互查询管理</h2>
        <p class="page-desc">维护交互查询语句的输入、执行约束与结果记录，为数据查询提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记查询语句</button>
        <button class="btn" type="button" @click="exportRows">导出交互查询清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="evidenceFocus" class="alert info" data-panel="evidence-focus">
      <strong>来自对比分析的样本证据：</strong>
      语句 {{ evidenceFocus.statement }} · 目标数据集「{{ evidenceFocus.dataset }}」
      <button class="link" type="button" @click="clearFocus">清除定位</button>
      <p class="hint" v-if="focusRow">
        证据记录：{{ focusRow['语句编号'] }} · {{ focusRow['查询表达式'] }}
      </p>
      <p class="hint" v-else>交互查询中没有找到该语句，可能已被归档。</p>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :class="{ 'focus-row': evidenceFocus && row['语句编号'] === evidenceFocus.statement }"
        >
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无交互查询数据，可先登记查询语句</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条交互查询记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const route = useRoute()
const router = useRouter()

const ENDPOINT = '/api/query'
const columns = ["语句编号", "查询表达式", "目标数据集", "返回字段", "排序条件", "分页大小", "最大行数", "超时秒数"]
const actions = ["提交执行", "启动查询", "终止查询", "保存结果"]
const statuses = ["草稿", "待执行", "执行中", "已完成", "已超时"]
const stats = [{"label": "查询语句总数", "value": 0}, {"label": "已完成查询", "value": 0}, {"label": "执行中查询", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const focusStatement = computed(() => String(route.query.statement ?? '').trim())
const focusDataset = computed(() => String(route.query.dataset ?? '').trim())
const evidenceFocus = computed(() =>
  focusStatement.value
    ? { statement: focusStatement.value, dataset: focusDataset.value }
    : null,
)
const focusRow = computed(() =>
  rows.value.find((row) => String(row['语句编号']) === focusStatement.value) ?? null,
)

function clearFocus() {
  void router.replace({ path: '/query' })
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '查询语句登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('交互查询动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '交互查询操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query: Record<string, string> = { ...filters.value }
  // 证据跳转时把页码放大，保证高亮语句落在可见页里。
  if (focusStatement.value && !query.keyword) query.keyword = focusStatement.value
  const search = new URLSearchParams(query).toString()
  try {
    const response = await request(`${ENDPOINT}?${search}`)
    if (!response.ok) {
      throw new Error('查询语句列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '交互查询列表读取失败'
  }
}

onMounted(reload)
</script>
