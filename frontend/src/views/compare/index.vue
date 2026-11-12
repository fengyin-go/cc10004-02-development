<template>
  <section class="page" data-module="compare">
    <header class="page-head">
      <div>
        <h2>对比分析管理</h2>
        <p class="page-desc">
          维护对比方案，并在同一页面完成成对样本差异矩阵：先确认基准与对照的字段映射，再按业务键配对，
          矩阵以颜色区分数值差、缺行与空值，双击格子可追溯样本证据。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记对比方案</button>
        <button class="btn" type="button" @click="exportRows">导出对比分析清单</button>
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

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          class="plan-row"
          :class="{ selected: selectedPlanId === Number(row.id) }"
          @click="selectPlan(row)"
        >
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td><span class="badge">{{ row.status }}</span></td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click.stop="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click.stop="openMapping(row)">字段映射</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无对比分析数据，可先登记对比方案</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条对比分析记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section v-if="selectedPlan" class="compare-workbench" data-panel="workbench-shell">
      <header class="workbench-head">
        <div>
          <h3>差异矩阵工作台 · {{ selectedPlan['方案编号'] }}</h3>
          <p class="page-desc">
            基准：{{ selectedPlan['基准数据集'] }}（{{ selectedPlan['基线数据集编号'] }}）
            ↔ 对照：{{ selectedPlan['对照数据集'] }}（{{ selectedPlan['对照数据集编号'] }}）
            · 对比指标：{{ selectedPlan['对比指标'] }}
            · 已有 {{ roundList.length }} 个比较轮次
          </p>
        </div>
        <button class="btn ghost" type="button" @click="closeWorkbench">收起工作台</button>
      </header>

      <MappingPanel
        v-if="mappingLoaded"
        :plan-id="selectedPlanId"
        :initial="mappingDetail"
        :datasets="datasetOptions"
        @saved="onMappingSaved"
      />
      <div v-else class="empty-state">正在读取字段映射…</div>

      <MatrixWorkspace :plan-id="selectedPlanId" @rounds-changed="onRoundsChanged" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

import MappingPanel from '@/views/compare/MappingPanel.vue'
import MatrixWorkspace from '@/views/compare/MatrixWorkspace.vue'
import * as api from '@/views/compare/api'
import type { Mapping, MappingDetail, RoundBrief } from '@/views/compare/types'

type Row = Record<string, string | number | null>
type PlanRecord = Record<string, string | number | null>

const ENDPOINT = '/api/compare'
const columns = ["方案编号", "基准数据集", "对照数据集", "对比维度", "对比指标", "差异阈值", "显著性水平", "输出展示"]
const actions = ["提交校验", "启用方案", "停用方案"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const statStats = [{"label": "对比方案总数", "value": 0}, {"label": "已启用方案", "value": 0}, {"label": "待校验方案", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = computed(() => [
  { label: statStats[0].label, value: total.value },
  { label: statStats[1].label, value: rows.value.filter((row) => row.status === statuses[2]).length },
  { label: statStats[2].label, value: rows.value.filter((row) => row.status === statuses[1]).length },
])

const selectedPlan = ref<PlanRecord | null>(null)
const selectedPlanId = computed(() => (selectedPlan.value ? Number(selectedPlan.value.id) : 0))
const mappingDetail = ref<MappingDetail | null>(null)
const mappingLoaded = ref(false)
const datasetOptions = ref<{ 数据集编号: string; 数据集名称: string; status: string }[]>([])
const roundList = ref<RoundBrief[]>([])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '对比方案登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '对比分析动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '对比分析操作失败'
  }
}

async function selectPlan(row: Row) {
  selectedPlan.value = row as PlanRecord
  mappingLoaded.value = false
  mappingDetail.value = null
  if (selectedPlanId.value) await loadMapping()
}

function openMapping(row: Row) {
  void selectPlan(row)
}

function closeWorkbench() {
  selectedPlan.value = null
  mappingDetail.value = null
  mappingLoaded.value = false
}

async function loadMapping() {
  try {
    const result = await api.mappingPreviewByPlan(selectedPlanId.value)
    mappingDetail.value = result
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '字段映射读取失败'
    mappingDetail.value = null
  } finally {
    mappingLoaded.value = true
  }
}

async function loadDatasets() {
  try {
    const response = await request('/api/datastore?size=200&status=已生效')
    const payload = await response.json()
    if (!response.ok) return
    let items = payload.items ?? []
    if (!items.length) {
      const all = await request('/api/datastore?size=200')
      items = (await all.json()).items ?? []
    }
    datasetOptions.value = items
  } catch {
    // 数据集缺失时映射面板会给出可读错误
  }
}

function onMappingSaved(payload: { mapping: Mapping; plan: Record<string, unknown> }) {
  if (!selectedPlan.value) return
  selectedPlan.value = {
    ...selectedPlan.value,
    基准数据集: String(payload.plan['基准数据集'] ?? selectedPlan.value['基准数据集']),
    对照数据集: String(payload.plan['对照数据集'] ?? selectedPlan.value['对照数据集']),
    基线数据集编号: String(payload.plan['基线数据集编号'] ?? selectedPlan.value['基线数据集编号']),
    对照数据集编号: String(payload.plan['对照数据集编号'] ?? selectedPlan.value['对照数据集编号']),
  }
}

function onRoundsChanged(rounds: RoundBrief[]) {
  roundList.value = rounds
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('对比方案列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '对比分析列表读取失败'
  }
}

onMounted(async () => {
  await reload()
  await loadDatasets()
})
</script>
