<template>
  <section class="mapping-panel" data-panel="mapping">
    <header class="panel-head">
      <div>
        <h3>第一步：确认基准与对照的字段映射</h3>
        <p class="panel-desc">
          从数据集管理中选定两条已生效数据集，再把业务键与数值字段一一对应。确认后的映射会登记回方案，
          之后每次比较都沿用这份字段身份。
        </p>
      </div>
      <div class="panel-actions">
        <button class="btn" type="button" :disabled="saving || !baseCode || !controlCode" @click="preview">
          推导字段
        </button>
        <button
          class="btn primary"
          type="button"
          :disabled="saving || !mappingValid"
          @click="save"
        >
          确认映射并登记
        </button>
      </div>
    </header>

    <div v-if="loadError" class="alert danger">{{ loadError }}</div>
    <div v-if="feedback" class="alert" :class="feedback.ok ? 'ok' : 'danger'">{{ feedback.text }}</div>

    <div class="dataset-picker">
      <label class="picker-item">
        <span>基准数据集</span>
        <select v-model="baseCode" :disabled="saving" @change="onDatasetChange">
          <option v-for="item in datasetOptions" :key="item.数据集编号" :value="item.数据集编号">
            {{ item.数据集编号 }} · {{ item.数据集名称 }}（{{ item.status }}）
          </option>
        </select>
      </label>
      <label class="picker-item">
        <span>对照数据集</span>
        <select v-model="controlCode" :disabled="saving" @change="onDatasetChange">
          <option v-for="item in datasetOptions" :key="item.数据集编号" :value="item.数据集编号">
            {{ item.数据集编号 }} · {{ item.数据集名称 }}（{{ item.status }}）
          </option>
        </select>
      </label>
      <div class="picker-note">
        <span class="badge" :class="sameDataset ? 'warn' : 'ok'">
          {{ sameDataset ? '基准与对照不能相同' : '两侧数据集不同' }}
        </span>
      </div>
    </div>

    <div v-if="draft" class="side-cards">
      <article v-for="side in sides" :key="side.code" class="side-card">
        <header>
          <strong>{{ side.role }}</strong>
          <span class="badge" :class="side.status === '已生效' ? 'ok' : 'warn'">{{ side.status }}</span>
        </header>
        <dl>
          <dt>数据集</dt><dd>{{ side.code }} · {{ side.name }}</dd>
          <dt>来源表</dt><dd>{{ side.source_table }}</dd>
        </dl>
        <div class="field-chips">
          <span v-for="field in side.fields" :key="field.name" class="field-chip">
            {{ field.label }}<em>{{ field.name }}</em>
          </span>
        </div>
      </article>
    </div>

    <div v-if="draft" class="mapping-editor">
      <section class="editor-block">
        <header class="block-head">
          <h4>业务键（用于跨数据集配对）</h4>
          <button class="link" type="button" @click="addKey">+ 追加业务键</button>
        </header>
        <div v-for="(key, index) in draft.mapping.business_keys" :key="`key-${index}`" class="pair-row">
          <label>
            <span>基准字段</span>
            <select v-model="key.base" @change="touch">
              <option v-for="field in baseFields" :key="field.name" :value="field.name">
                {{ field.label }}（{{ field.name }}）
              </option>
            </select>
          </label>
          <span class="arrow">↔</span>
          <label>
            <span>对照字段</span>
            <select v-model="key.control" @change="touch">
              <option v-for="field in controlFields" :key="field.name" :value="field.name">
                {{ field.label }}（{{ field.name }}）
              </option>
            </select>
          </label>
          <label class="label-input">
            <span>业务键名称</span>
            <input v-model="key.label" @input="touch" />
          </label>
          <button class="link danger" type="button" :disabled="draft.mapping.business_keys.length <= 1" @click="removeKey(index)">
            删除
          </button>
        </div>
        <p class="hint">
          配对只认业务键。任一侧同键出现多行时，整组进入隔离区等待人工裁决，不会按输入顺序自动配对。
        </p>
      </section>

      <section class="editor-block">
        <header class="block-head">
          <h4>数值对比字段</h4>
          <button class="link" type="button" @click="addValue">+ 追加字段</button>
        </header>
        <div class="pair-table">
          <div class="pair-table-head">
            <span>基准字段</span><span>对照字段</span><span>展示名</span><span>差异阈值</span><span>阈值说明</span><span></span>
          </div>
          <div v-for="(field, index) in draft.mapping.value_fields" :key="`value-${index}`" class="pair-table-row">
            <select v-model="field.base" @change="touch">
              <option v-for="candidate in baseFields" :key="candidate.name" :value="candidate.name">
                {{ candidate.label }}（{{ candidate.name }}）
              </option>
            </select>
            <select v-model="field.control" @change="touch">
              <option v-for="candidate in controlFields" :key="candidate.name" :value="candidate.name">
                {{ candidate.label }}（{{ candidate.name }}）
              </option>
            </select>
            <input v-model="field.label" @input="touch" />
            <input v-model.number="field.threshold" type="number" step="any" min="0" @input="touch" />
            <span class="threshold-note">|对照 - 基准| ≤ {{ field.threshold }} 视为阈值内</span>
            <button class="link danger" type="button" :disabled="draft.mapping.value_fields.length <= 1" @click="removeValue(index)">
              删除
            </button>
          </div>
        </div>
        <p class="hint">阈值按绝对差值判断：空字符串、null 与数字 0 是不同取值，不会被折算成同一数字。</p>
      </section>
    </div>

    <div v-else class="empty-state">
      {{ loading ? '正在读取字段定义…' : '请选择基准与对照数据集后推导字段映射' }}
    </div>

    <div v-if="draft && validationIssues.length" class="alert danger">
      <strong>映射不成立：</strong>
      <ul>
        <li v-for="issue in validationIssues" :key="issue">{{ issue }}</li>
      </ul>
    </div>
    <div v-else-if="draft" class="alert ok">
      映射校验通过：{{ draft.mapping.business_keys.length }} 个业务键、{{ draft.mapping.value_fields.length }} 个数值字段。
      来源：{{ draft.mapping_source }}
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import * as api from './api'
import type { Mapping, MappingDetail } from './types'

type DatasetOption = {
  数据集编号: string
  数据集名称: string
  status: string
}

const props = defineProps<{
  planId: number
  initial: MappingDetail | null
  datasets: DatasetOption[]
}>()

const emit = defineEmits<{
  (event: 'saved', payload: { mapping: Mapping; plan: Record<string, unknown> }): void
}>()

const baseCode = ref('')
const controlCode = ref('')
const draft = ref<MappingDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const feedback = ref<{ ok: boolean; text: string } | null>(null)

const baseFields = computed(() => draft.value?.base_dataset.fields ?? [])
const controlFields = computed(() => draft.value?.control_dataset.fields ?? [])
const sameDataset = computed(() => Boolean(baseCode.value) && baseCode.value === controlCode.value)
const sides = computed(() =>
  draft.value
    ? [
        { role: '基准', ...draft.value.base_dataset },
        { role: '对照', ...draft.value.control_dataset },
      ]
    : [],
)

const validationIssues = computed(() => {
  if (!draft.value) return []
  const issues = [...(draft.value.validation ?? [])]
  if (sameDataset.value) issues.push('基准与对照不能选择同一个数据集')
  if (!draft.value.mapping.business_keys.length) issues.push('至少需要一个业务键字段')
  if (!draft.value.mapping.value_fields.length) issues.push('至少需要一个数值对比字段')
  draft.value.mapping.business_keys.forEach((key, index) => {
    if (!key.base || !key.control) issues.push(`第 ${index + 1} 个业务键未选齐两侧字段`)
  })
  draft.value.mapping.value_fields.forEach((field, index) => {
    if (!field.base || !field.control) issues.push(`第 ${index + 1} 个数值字段未选齐两侧字段`)
    const threshold = Number(field.threshold)
    if (!Number.isFinite(threshold) || threshold < 0) {
      issues.push(`第 ${index + 1} 个数值字段的阈值必须是非负数值`)
    }
  })
  return issues
})
const mappingValid = computed(() => Boolean(draft.value) && validationIssues.value.length === 0)

function applyDetail(detail: MappingDetail) {
  draft.value = detail
  baseCode.value = detail.base_dataset.code
  controlCode.value = detail.control_dataset.code
}

async function preview() {
  if (!baseCode.value || !controlCode.value) return
  loading.value = true
  loadError.value = ''
  feedback.value = null
  try {
    applyDetail(await api.mappingPreview(baseCode.value, controlCode.value))
  } catch (error) {
    draft.value = null
    loadError.value = error instanceof Error ? error.message : '字段映射推导失败'
  } finally {
    loading.value = false
  }
}

function onDatasetChange() {
  draft.value = null
  // 换了数据集就立刻按字段标签推导一版，避免用户对着旧字段确认映射。
  void preview()
}

async function loadDatasetsFromStore() {
  // 数据集列表由父组件传入；这里只处理父组件还没拿到时的兜底。
  try {
    const response = await fetch('/api/datastore?size=200')
    if (!response.ok) return
    const payload = (await response.json()) as { items?: DatasetOption[] }
    if (payload.items?.length) datasetsFallback.value = payload.items
    if (!baseCode.value && payload.items?.[0]) baseCode.value = payload.items[0].数据集编号
    if (!controlCode.value && payload.items?.[1]) controlCode.value = payload.items[1].数据集编号
  } catch {
    // 父组件会展示更明确的错误
  }
}

const datasetsFallback = ref<DatasetOption[]>([])
const datasetOptions = computed(() => (props.datasets.length ? props.datasets : datasetsFallback.value))

function addKey() {
  draft.value?.mapping.business_keys.push({ base: '', control: '', label: '业务键' })
}

function removeKey(index: number) {
  draft.value?.mapping.business_keys.splice(index, 1)
}

function addValue() {
  draft.value?.mapping.value_fields.push({
    base: '',
    control: '',
    label: '对比字段',
    threshold: 0,
    threshold_mode: 'absolute',
  })
}

function removeValue(index: number) {
  draft.value?.mapping.value_fields.splice(index, 1)
}

function touch() {
  // 触发 computed 重新校验；具体值由 v-model 已写入 draft。
}

async function save() {
  if (!draft.value || !mappingValid.value) return
  saving.value = true
  loadError.value = ''
  try {
    const result = await api.saveMapping(props.planId, baseCode.value, controlCode.value, draft.value.mapping)
    if (!result.ok) throw new Error(result.message)
    feedback.value = { ok: true, text: result.message }
    // 用后端返回的方案作为新的初始值，避免再次打开时又回到旧映射。
    draft.value = {
      ...draft.value,
      mapping_source: '方案已登记字段映射',
      validation: [],
    }
    emit('saved', {
      mapping: draft.value.mapping,
      plan: (result.entry as Record<string, unknown>) ?? {},
    })
  } catch (error) {
    feedback.value = { ok: false, text: error instanceof Error ? error.message : '字段映射保存失败' }
  } finally {
    saving.value = false
  }
}

async function init() {
  loading.value = true
  try {
    if (props.initial) {
      applyDetail(props.initial)
    }
    await loadDatasetsFromStore()
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void init()
})
</script>
