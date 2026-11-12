<template>
  <section class="workbench" data-panel="workspace">
    <header class="panel-head">
      <div>
        <h3>第二步：启动比较并查看成对样本差异矩阵</h3>
        <p class="panel-desc">
          启动时封存两侧定义与字段身份；矩阵按业务键配对，颜色分别表达数值差、缺行与空值。
          双击格子可跨模块打开交互查询里的样本证据。
        </p>
      </div>
      <div class="panel-actions">
        <button class="btn primary" type="button" :disabled="busy" @click="startRound">
          启动比较（封存两侧）
        </button>
        <button class="btn" type="button" :disabled="busy || !currentRound" @click="recompute">
          重算（开启新轮次）
        </button>
        <button class="btn" type="button" :disabled="busy || !currentRound" @click="swap">
          左右交换
        </button>
        <button class="btn" type="button" :disabled="busy || !currentRound || currentRound.status === '已签认'" @click="signoff">
          签认结论
        </button>
      </div>
    </header>

    <div v-if="message" class="alert" :class="message.ok ? 'ok' : 'danger'">{{ message.text }}</div>
    <div v-if="loadingRounds" class="empty-state">正在读取比较轮次…</div>

    <div class="round-layout">
      <aside class="round-list">
        <h4>比较轮次</h4>
        <button
          v-for="round in rounds"
          :key="round.id"
          class="round-item"
          :class="{ active: currentRound?.id === round.id }"
          type="button"
          @click="selectRound(round)"
        >
          <span class="round-title">第 {{ round.round_no }} 轮</span>
          <span class="badge" :class="statusTone(round.status)">{{ round.status }}</span>
          <span class="round-sub">
            {{ formatTime(round.created_at) }}
            <template v-if="round.swap_of"> · 交换自第 {{ round.swap_of }} 轮</template>
          </span>
        </button>
        <p v-if="!rounds.length" class="muted small">还没有轮次，先确认字段映射再启动比较。</p>
      </aside>

      <div class="round-main">
        <template v-if="currentRound">
          <div class="snapshot-strip">
            <div class="snapshot-side">
              <span class="muted">基准（封存于 {{ formatTime(currentRound.snapshot.sealed_at) }}）</span>
              <strong>{{ currentRound.snapshot.base.name }}</strong>
              <span class="mono small">{{ currentRound.snapshot.base.code }} · {{ currentRound.snapshot.base.source_table }}</span>
              <span class="badge" :class="currentRound.snapshot.base.status_at_seal === '已生效' ? 'ok' : 'warn'">
                {{ currentRound.snapshot.base.status_at_seal }}
              </span>
              <span class="mono small">摘要 {{ shortDigest(currentRound.snapshot.base.digest) }}</span>
            </div>
            <div class="snapshot-arrow">
              <span class="muted">{{ currentRound.snapshot.diff_direction }}</span>
              <span class="digest mono">轮次摘要 {{ shortDigest(currentRound.snapshot.digest) }}</span>
            </div>
            <div class="snapshot-side">
              <span class="muted">对照（封存于 {{ formatTime(currentRound.snapshot.sealed_at) }}）</span>
              <strong>{{ currentRound.snapshot.control.name }}</strong>
              <span class="mono small">{{ currentRound.snapshot.control.code }} · {{ currentRound.snapshot.control.source_table }}</span>
              <span class="badge" :class="currentRound.snapshot.control.status_at_seal === '已生效' ? 'ok' : 'warn'">
                {{ currentRound.snapshot.control.status_at_seal }}
              </span>
              <span class="mono small">摘要 {{ shortDigest(currentRound.snapshot.control.digest) }}</span>
            </div>
          </div>

          <div v-if="currentRound.status === '计算中'" class="alert info">
            两侧定义已封存，矩阵尚未生成。
            <button class="link" type="button" :disabled="busy" @click="complete">完成计算</button>
          </div>
          <div v-if="currentRound.block_reasons.length" class="alert danger">
            <strong>结论签认已阻断：</strong>
            <ul><li v-for="reason in currentRound.block_reasons" :key="reason">{{ reason }}</li></ul>
          </div>
          <div v-if="currentRound.warnings.length" class="alert warn">
            <strong>定义变化提示：</strong>
            <ul><li v-for="warning in currentRound.warnings" :key="warning">{{ warning }}</li></ul>
          </div>
          <div v-if="currentRound.signed" class="alert ok">
            已于 {{ formatTime(currentRound.signed.at) }} 签认：{{ currentRound.signed.note }}
            （快照摘要 {{ shortDigest(currentRound.signed.snapshot_digest) }}）
          </div>
          <div v-if="currentRound.parent_round_id" class="alert info">
            本轮为重算轮次，独立于第 {{ currentRound.parent_round_id }} 轮；原轮次仍保有当时的字段身份与阈值。
          </div>

          <div class="summary-row">
            <article v-for="item in summaryCards" :key="item.label" class="summary-card" :class="item.tone">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </article>
          </div>

          <div v-if="currentRound.mapping.business_keys.length" class="mapping-strip">
            <span class="muted">业务键：</span>
            <span v-for="key in currentRound.mapping.business_keys" :key="key.label" class="badge">
              {{ key.label }} {{ key.base }} ↔ {{ key.control }}
            </span>
            <span class="muted">阈值：</span>
            <span v-for="field in currentRound.mapping.value_fields" :key="field.label" class="badge muted">
              {{ field.label }} ≤ {{ field.threshold }}
            </span>
          </div>

          <section class="quarantine" data-panel="quarantine">
            <header class="block-head">
              <h4>隔离区 · 歧义键组（{{ quarantineGroups.length }}）</h4>
              <span class="muted small">业务键重复的组不会按输入顺序配对，必须逐组确认或整组跳过</span>
            </header>
            <p v-if="!quarantineGroups.length" class="muted small">本轮的键都能唯一配对，隔离区为空。</p>
            <div v-for="group in quarantineGroups" :key="group.group_id" class="quarantine-group">
            <header>
              <span class="badge warn">{{ group.group_id }}</span>
              <strong class="mono">{{ group.key }}</strong>
              <span class="muted">{{ group.reason }}</span>
              <span v-if="group.resolution" class="badge signed">
                已裁决：{{ group.resolution.decision }}
                <template v-if="group.resolution.base_record_id">
                  （{{ group.resolution.base_record_id }} ↔ {{ group.resolution.control_record_id ?? '缺行' }}）
                </template>
              </span>
            </header>
            <div v-if="!group.resolution" class="quarantine-body">
              <div class="quarantine-sides">
                <div class="quarantine-side">
                  <span class="muted">基准侧{{ group.base_records.length ? '' : '（整侧缺行）' }}</span>
                  <label v-for="record in group.base_records" :key="record.record_id" class="record-option">
                    <input v-model="drafts[group.group_id].base" type="radio" :value="record.record_id" />
                    <span class="mono">{{ record.record_id }}</span>
                    <span class="record-values">{{ recordSummary(record.values) }}</span>
                  </label>
                  <p v-if="!group.base_records.length" class="muted small">该键在基准侧没有记录</p>
                </div>
                <div class="quarantine-side">
                  <span class="muted">对照侧{{ group.control_records.length ? '' : '（整侧缺行）' }}</span>
                  <label v-for="record in group.control_records" :key="record.record_id" class="record-option">
                    <input v-model="drafts[group.group_id].control" type="radio" :value="record.record_id" />
                    <span class="mono">{{ record.record_id }}</span>
                    <span class="record-values">{{ recordSummary(record.values) }}</span>
                  </label>
                  <p v-if="!group.control_records.length" class="muted small">该键在对照侧没有记录</p>
                </div>
              </div>
              <div class="quarantine-actions">
                <input v-model="drafts[group.group_id].note" placeholder="裁决备注（可选）" />
                <button
                  class="btn primary"
                  type="button"
                  :disabled="busy || !canConfirm(group)"
                  @click="decide(group, '确认配对')"
                >
                  确认这两条配对
                </button>
                <button class="btn" type="button" :disabled="busy" @click="decide(group, '整组不比较')">
                  整组不比较
                </button>
              </div>
              <p class="hint">
                必须显式点选两侧各一条记录（整侧缺行时只选存在的一侧）；不选记录不会自动按顺序配对。
              </p>
            </div>
          </div>
          </section>

          <section v-if="matrix" class="matrix-section" data-panel="matrix">
            <header class="block-head">
              <h4>差异矩阵（{{ matrix.total }} 组配对 · 修订 {{ matrix.matrix_revision }}）</h4>
              <div class="matrix-controls">
                <select v-model="stateFilter" @change="reloadMatrix(1)">
                  <option value="all">全部状态</option>
                  <option value="diff">仅数值差</option>
                  <option value="missing">仅缺行</option>
                  <option value="null">仅空值</option>
                </select>
                <input v-model="keyword" placeholder="按业务键/记录号检索" @keydown.enter.prevent="reloadMatrix(1)" />
                <button class="btn" type="button" @click="reloadMatrix(1)">查询</button>
              </div>
            </header>

            <div class="legend-row">
              <span v-for="item in matrix.legend" :key="item.state" class="legend-item">
                <i class="swatch" :class="`cell-${item.state}`"></i>{{ item.label }}
              </span>
            </div>

            <div class="matrix-head">
              <span>业务键 / 配对状态</span>
              <span class="matrix-columns">
                <span v-for="column in matrix.columns" :key="column.label" class="matrix-column">
                  {{ column.label }}
                  <em>{{ column.base }} ↔ {{ column.control }}（阈值 {{ column.threshold }}）</em>
                </span>
              </span>
            </div>

            <MatrixGrid
              :pairs="matrix.items"
              :selected-cell-id="selectedCell?.cell.cell_id ?? null"
              @select="selectCell"
              @open-evidence="openEvidence"
            />

            <footer class="matrix-foot">
              <span class="muted">
                第 {{ matrix.page }} 页 · 共 {{ matrix.total }} 组 · 每页 {{ matrix.size }} 组
              </span>
              <div class="pager">
                <button class="btn" type="button" :disabled="matrix.page <= 1 || loadingMatrix" @click="reloadMatrix(matrix.page - 1)">
                  上一页
                </button>
                <button
                  class="btn"
                  type="button"
                  :disabled="matrix.page * matrix.size >= matrix.total || loadingMatrix"
                  @click="reloadMatrix(matrix.page + 1)"
                >
                  下一页
                </button>
              </div>
            </footer>
          </section>

          <section v-if="selectedCell" class="cell-inspector" data-panel="inspector">
            <header class="block-head">
              <h4>格子 {{ selectedCell.cell.cell_id }} · {{ selectedCell.cell.label }}</h4>
              <button class="btn" type="button" @click="openEvidence(selectedCell)">双击查看样本证据</button>
            </header>
            <div class="inspector-grid">
              <div><span class="muted">基准</span><strong class="mono">{{ displayRaw(selectedCell.cell.base_raw) }}</strong></div>
              <div><span class="muted">对照</span><strong class="mono">{{ displayRaw(selectedCell.cell.control_raw) }}</strong></div>
              <div><span class="muted">差值（对照 - 基准）</span><strong class="mono">{{ selectedCell.cell.display }}</strong></div>
              <div><span class="muted">状态</span><strong>{{ CELL_STATUS_LABELS[selectedCell.cell.status] }}</strong></div>
              <div><span class="muted">匹配依据</span><strong>{{ selectedCell.pair.match_basis }}</strong></div>
              <div><span class="muted">业务键</span><strong class="mono">{{ selectedCell.pair.key }}</strong></div>
            </div>
            <p v-if="selectedCell.cell.null_note" class="hint">{{ selectedCell.cell.null_note }}</p>
          </section>

          <section class="history-section">
            <header class="block-head"><h4>轮次状态流转</h4></header>
            <ol class="history-list">
              <li v-for="(step, index) in currentRound.status_history" :key="`${step.status}-${index}`">
                <span class="badge" :class="statusTone(step.status)">{{ step.status }}</span>
                <span>{{ formatTime(step.at) }}</span>
                <span class="muted">{{ step.note }}</span>
              </li>
            </ol>
          </section>
        </template>
        <div v-else class="empty-state">选择左侧轮次查看矩阵，或直接启动新一轮比较。</div>
      </div>
    </div>

    <EvidenceDialog
      :open="evidenceOpen"
      :round-id="currentRound?.id ?? 0"
      :cell-id="evidenceCell?.cell_id ?? null"
      :cell="evidenceCell"
      :snapshot-direction="currentRound?.snapshot.diff_direction ?? '对照 - 基准'"
      @close="evidenceOpen = false"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import * as api from './api'
import EvidenceDialog from './EvidenceDialog.vue'
import MatrixGrid from './MatrixGrid.vue'
import { CELL_STATUS_LABELS, displayRaw, formatTime, shortDigest, statusTone } from './format'
import type { Cell, MatrixPage, Pair, QuarantineGroup, RoundBrief, RoundDetail } from './types'

const props = defineProps<{ planId: number | null }>()
const emit = defineEmits<{ (event: 'rounds-changed', rounds: RoundBrief[]): void }>()

const rounds = ref<RoundBrief[]>([])
const currentRound = ref<RoundDetail | null>(null)
const matrix = ref<MatrixPage | null>(null)
const loadingRounds = ref(false)
const loadingMatrix = ref(false)
const busy = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)
const stateFilter = ref('all')
const keyword = ref('')
const selectedCell = ref<{ pair: Pair; cell: Cell } | null>(null)
const evidenceOpen = ref(false)
const evidenceCell = ref<Cell | null>(null)
const drafts = reactive<Record<string, { base: string; control: string; note: string }>>({})

const quarantineGroups = computed(() => currentRound.value?.quarantine_groups ?? [])
const summaryCards = computed(() => {
  const summary = currentRound.value?.summary
  if (!summary) return []
  return [
    { label: '配对组数', value: summary.pair_count, tone: '' },
    { label: '数值差', value: summary.diff_cells, tone: 'tone-danger' },
    { label: '缺行', value: summary.missing_cells, tone: 'tone-warn' },
    { label: '空值', value: summary.null_cells, tone: 'tone-null' },
    { label: '阈值内', value: summary.within_cells, tone: 'tone-ok' },
    { label: '隔离键组', value: summary.quarantine_groups, tone: summary.unresolved_quarantine_groups ? 'tone-warn' : 'tone-ok' },
  ]
})

watch(
  () => props.planId,
  () => void reloadRounds(),
  { immediate: true },
)

async function reloadRounds() {
  if (!props.planId) {
    rounds.value = []
    currentRound.value = null
    matrix.value = null
    return
  }
  loadingRounds.value = true
  try {
    const payload = await api.fetchRounds(props.planId)
    rounds.value = payload.items ?? []
    emit('rounds-changed', rounds.value)
    const targetId = currentRound.value?.id ?? rounds.value[0]?.id
    if (targetId) await loadRound(targetId)
    else {
      currentRound.value = null
      matrix.value = null
    }
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '轮次读取失败' }
  } finally {
    loadingRounds.value = false
  }
}

async function loadRound(roundId: number) {
  currentRound.value = await api.fetchRound(roundId)
  ensureDrafts()
  selectedCell.value = null
  if (currentRound.value.pairs_total > 0) {
    await reloadMatrix(1)
  } else {
    matrix.value = null
  }
}

function ensureDrafts() {
  for (const group of quarantineGroups.value) {
    if (!drafts[group.group_id]) {
      drafts[group.group_id] = { base: '', control: '', note: '' }
    }
  }
}

/** 存在的一侧必须点选；整侧缺行时允许留空，结果按缺行格子展示。 */
function canConfirm(group: QuarantineGroup): boolean {
  const draft = drafts[group.group_id]
  if (!draft) return false
  const baseOk = group.base_records.length === 0 || Boolean(draft.base)
  const controlOk = group.control_records.length === 0 || Boolean(draft.control)
  return baseOk && controlOk && (group.base_records.length > 0 || group.control_records.length > 0)
}

async function selectRound(round: RoundBrief) {
  busy.value = true
  message.value = null
  try {
    await loadRound(round.id)
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '轮次读取失败' }
  } finally {
    busy.value = false
  }
}

async function startRound() {
  if (!props.planId) return
  busy.value = true
  message.value = null
  try {
    await doStartRound()
  } finally {
    busy.value = false
  }
}

/** 启动后立即完成计算，让用户直接看到矩阵；轮次本身仍是可追溯的封存快照。 */
async function doStartRound(parentRoundId: number | null = null) {
  const result = await api.createRound(props.planId as number, parentRoundId)
  if (!result.ok) throw new Error(result.message)
  const created = result.entry as RoundBrief
  await api.completeRound(created.id)
  message.value = { ok: true, text: `${result.message}，矩阵已生成` }
  await reloadRounds()
  await loadRound(created.id)
}

/** 重算：开启独立轮次，旧轮次的快照、字段身份和阈值保持不变。 */
async function recompute() {
  if (!currentRound.value) return
  const parentId = currentRound.value.id
  const parentNo = currentRound.value.round_no
  busy.value = true
  message.value = null
  try {
    await doStartRound(parentId)
    message.value = {
      ok: true,
      text: `已开启独立重算轮次；第 ${parentNo} 轮仍保留当时的字段身份与阈值`,
    }
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '重算失败' }
  } finally {
    busy.value = false
  }
}

async function complete() {
  if (!currentRound.value) return
  busy.value = true
  try {
    const result = await api.completeRound(currentRound.value.id)
    if (!result.ok) throw new Error(result.message)
    message.value = { ok: true, text: result.message }
    await reloadRounds()
    await loadRound(currentRound.value.id)
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '矩阵计算失败' }
  } finally {
    busy.value = false
  }
}

async function reloadMatrix(page: number) {
  if (!currentRound.value) return
  loadingMatrix.value = true
  try {
    matrix.value = await api.fetchMatrix(currentRound.value.id, {
      page,
      size: 20,
      state: stateFilter.value,
      keyword: keyword.value,
    })
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '矩阵取数失败' }
  } finally {
    loadingMatrix.value = false
  }
}

function selectCell(payload: { pair: Pair; cell: Cell }) {
  selectedCell.value = payload
}

function openEvidence(payload: { pair: Pair; cell: Cell }) {
  selectedCell.value = payload
  evidenceCell.value = payload.cell
  evidenceOpen.value = true
}

async function decide(group: QuarantineGroup, decision: string) {
  if (!currentRound.value) return
  const draft = drafts[group.group_id]
  if (decision === '确认配对' && !canConfirm(group)) {
    message.value = { ok: false, text: '确认配对必须显式点选存在的一侧记录' }
    return
  }
  busy.value = true
  try {
    const result = await api.resolveQuarantine(currentRound.value.id, group.group_id, {
      decision,
      // 整侧缺行时不传该侧记录，后端按缺行配对处理；不传不等于按顺序挑一条。
      base_record_id: decision === '确认配对' ? draft.base || undefined : undefined,
      control_record_id: decision === '确认配对' ? draft.control || undefined : undefined,
      note: draft.note,
    })
    if (!result.ok) throw new Error(result.message)
    message.value = { ok: true, text: result.message }
    await loadRound(currentRound.value.id)
    await reloadRounds()
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '隔离区裁决失败' }
  } finally {
    busy.value = false
  }
}

async function swap() {
  if (!currentRound.value) return
  busy.value = true
  message.value = null
  try {
    const result = await api.swapRound(currentRound.value.id)
    if (!result.ok) throw new Error(result.message)
    const swapped = result.entry as RoundBrief
    await api.completeRound(swapped.id)
    message.value = { ok: true, text: `${result.message}，矩阵已生成` }
    await reloadRounds()
    await loadRound(swapped.id)
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '左右交换失败' }
  } finally {
    busy.value = false
  }
}

async function signoff() {
  if (!currentRound.value) return
  const note = window.prompt('签认备注（可选）', '') ?? ''
  busy.value = true
  try {
    const result = await api.signoffRound(currentRound.value.id, note)
    if (!result.ok) throw new Error(result.message)
    message.value = { ok: true, text: result.message }
    await reloadRounds()
    await loadRound(currentRound.value.id)
  } catch (error) {
    message.value = { ok: false, text: error instanceof Error ? error.message : '结论签认失败' }
  } finally {
    busy.value = false
  }
}

function recordSummary(values: Record<string, unknown>): string {
  return Object.entries(values)
    .slice(0, 4)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(' · ')
}
</script>
