<template>
  <div v-if="open" class="dialog-mask" @click.self="close">
    <section class="dialog" role="dialog" aria-modal="true" data-dialog="cell-evidence">
      <header class="dialog-head">
        <div>
          <h3>格子 {{ cellId }}</h3>
          <p class="dialog-sub">
            业务键 <strong>{{ evidence?.key || cell?.label }}</strong>
            · {{ evidence?.match_basis || '匹配依据读取中' }}
          </p>
        </div>
        <button class="btn ghost" type="button" @click="close">关闭</button>
      </header>

      <div v-if="loading" class="dialog-body">正在读取样本证据…</div>
      <div v-else-if="error" class="dialog-body"><div class="alert danger">{{ error }}</div></div>

      <div v-else-if="evidence && cell" class="dialog-body">
        <nav class="tab-row">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab"
            :class="{ active: activeTab === tab.key }"
            type="button"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </nav>

        <div v-if="activeTab === 'evidence'" class="tab-panel">
          <div class="cell-summary" :class="`cell-${cell.status}`">
            <span class="cell-state">{{ CELL_STATUS_LABELS[cell.status] }}</span>
            <span class="mono">{{ cell.display }}</span>
            <span v-if="cell.null_note" class="muted">{{ cell.null_note }}</span>
            <span class="muted">
              阈值 |对照 - 基准| ≤ {{ cell.threshold }}；方向：{{ snapshotDirection }}
            </span>
          </div>

          <div class="evidence-grid">
            <article class="evidence-card">
              <header>
                <strong>{{ evidence.base.role }}</strong>
                <span class="badge">{{ evidence.base.dataset_name }}</span>
                <span class="badge muted">{{ evidence.base.source_table }}</span>
              </header>
              <dl>
                <dt>记录编号</dt><dd class="mono">{{ evidence.base.record_id ?? '（缺行）' }}</dd>
                <dt>字段</dt><dd class="mono">{{ cell.base_field }} · {{ displayKind(cell.base_kind) }}</dd>
                <dt>取值</dt><dd class="mono strong">{{ displayRaw(cell.base_raw) }}</dd>
                <dt>封存摘要</dt><dd class="mono">{{ shortDigest(evidence.base.sealed_digest) }}</dd>
              </dl>
              <div class="query-block">
                <span class="muted">交互查询语句</span>
                <template v-if="evidence.queries.base">
                  <p class="mono small">{{ evidence.queries.base.statement_no }} · {{ evidence.queries.base.status }}</p>
                  <pre class="code">{{ evidence.queries.base.expression }}</pre>
                  <button class="btn" type="button" @click="openQuery(evidence.queries.base)">
                    在交互查询中打开
                  </button>
                </template>
                <p v-else class="muted">该数据集在交互查询中没有登记的语句</p>
              </div>
            </article>

            <article class="evidence-card">
              <header>
                <strong>{{ evidence.control.role }}</strong>
                <span class="badge">{{ evidence.control.dataset_name }}</span>
                <span class="badge muted">{{ evidence.control.source_table }}</span>
              </header>
              <dl>
                <dt>记录编号</dt><dd class="mono">{{ evidence.control.record_id ?? '（缺行）' }}</dd>
                <dt>字段</dt><dd class="mono">{{ cell.control_field }} · {{ displayKind(cell.control_kind) }}</dd>
                <dt>取值</dt><dd class="mono strong">{{ displayRaw(cell.control_raw) }}</dd>
                <dt>封存摘要</dt><dd class="mono">{{ shortDigest(evidence.control.sealed_digest) }}</dd>
              </dl>
              <div class="query-block">
                <span class="muted">交互查询语句</span>
                <template v-if="evidence.queries.control">
                  <p class="mono small">{{ evidence.queries.control.statement_no }} · {{ evidence.queries.control.status }}</p>
                  <pre class="code">{{ evidence.queries.control.expression }}</pre>
                  <button class="btn" type="button" @click="openQuery(evidence.queries.control)">
                    在交互查询中打开
                  </button>
                </template>
                <p v-else class="muted">该数据集在交互查询中没有登记的语句</p>
              </div>
            </article>
          </div>
        </div>

        <div v-else-if="activeTab === 'trace'" class="tab-panel">
          <div v-if="detail" class="trace-grid">
            <dl class="trace-list">
              <dt>匹配依据</dt><dd>{{ detail.trace.match_basis }}</dd>
              <dt>行状态</dt><dd>{{ rowStateLabel(detail.trace.row_state) }}</dd>
              <dt>业务键</dt>
              <dd>
                <span v-for="key in detail.trace.business_keys" :key="key.label" class="badge">
                  {{ key.label }}：{{ key.base }} ↔ {{ key.control }}
                </span>
              </dd>
              <dt>基准记录</dt><dd class="mono">{{ detail.trace.base_record_id ?? '（缺行）' }}</dd>
              <dt>对照记录</dt><dd class="mono">{{ detail.trace.control_record_id ?? '（缺行）' }}</dd>
              <dt>字段映射</dt>
              <dd class="mono">{{ detail.trace.field_mapping.base }} ↔ {{ detail.trace.field_mapping.control }}</dd>
              <dt>阈值</dt><dd>{{ detail.trace.threshold ?? '—' }}（绝对差）</dd>
              <dt>差值方向</dt><dd>{{ detail.trace.diff_direction }}</dd>
              <dt>人工裁决</dt><dd>{{ detail.trace.adjudicated ? '是（隔离区确认配对）' : '否' }}</dd>
              <dt>轮次 / 修订</dt><dd>第 {{ detail.trace.round_no }} 轮 · 矩阵修订 {{ detail.trace.matrix_revision }}</dd>
              <dt>封存时间</dt><dd>{{ formatTime(detail.trace.sealed_at) }}</dd>
              <dt>封存摘要</dt><dd class="mono">{{ shortDigest(detail.trace.snapshot_digest) }}</dd>
            </dl>
            <div class="trace-identities">
              <article v-for="side in [detail.trace.base_definition, detail.trace.control_definition]" :key="side.role" class="identity-card">
                <header><strong>{{ side.role }}</strong> <span class="badge" :class="side.status_at_seal === '已生效' ? 'ok' : 'warn'">{{ side.status_at_seal }}</span></header>
                <p>{{ side.code }} · {{ side.name }}</p>
                <p class="muted mono">{{ side.source_table }} · {{ side.record_count }} 行</p>
                <p class="muted mono">定义摘要 {{ shortDigest(side.digest) }}</p>
              </article>
            </div>
          </div>
          <div v-else class="muted">正在读取追溯信息…</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useRouter } from 'vue-router'

import * as api from './api'
import { CELL_STATUS_LABELS, displayKind, displayRaw, formatTime, rowStateLabel, shortDigest } from './format'
import type { Cell, CellDetail, CellEvidence, QueryEvidence } from './types'

const props = defineProps<{
  open: boolean
  roundId: number
  cellId: string | null
  cell: Cell | null
  snapshotDirection: string
}>()

const emit = defineEmits<{ (event: 'close'): void }>()

const router = useRouter()
const evidence = ref<CellEvidence | null>(null)
const detail = ref<CellDetail | null>(null)
const loading = ref(false)
const error = ref('')
const activeTab = ref<'evidence' | 'trace'>('evidence')

const tabs = [
  { key: 'evidence' as const, label: '样本证据' },
  { key: 'trace' as const, label: '匹配依据与封存身份' },
]

const currentCell = computed(() => evidence.value?.cell ?? props.cell)

const load = async () => {
  if (!props.open || !props.cellId) return
  loading.value = true
  error.value = ''
  evidence.value = null
  detail.value = null
  activeTab.value = 'evidence'
  try {
    const [evidenceResult, detailResult] = await Promise.all([
      api.fetchCellEvidence(props.roundId, props.cellId),
      api.fetchCellDetail(props.roundId, props.cellId),
    ])
    evidence.value = evidenceResult
    detail.value = detailResult
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '样本证据读取失败'
  } finally {
    loading.value = false
  }
}

watch(() => [props.open, props.cellId, props.roundId], () => void load(), { immediate: true })

function close() {
  emit('close')
}

function openQuery(query: QueryEvidence) {
  close()
  void router.push({
    path: '/query',
    query: { statement: query.statement_no, dataset: query.target_dataset, from: 'compare' },
  })
}
</script>
