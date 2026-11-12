<template>
  <article v-for="pair in pairs" :key="pair.pair_id" class="matrix-row" :data-pair="pair.pair_id">
    <div class="row-meta">
      <span class="mono key">{{ pair.key }}</span>
      <span class="badge" :class="rowTone(pair.row_state)">{{ rowStateLabel(pair.row_state) }}</span>
      <span v-if="pair.adjudicated" class="badge signed">人工裁决</span>
    </div>
    <div class="row-cells">
      <button
        v-for="cell in pair.cells"
        :key="cell.cell_id"
        class="matrix-cell"
        :class="[`cell-${cell.status}`, { selected: selectedCellId === cell.cell_id }]"
        type="button"
        :title="`${cell.label}：基准 ${displayRaw(cell.base_raw)} / 对照 ${displayRaw(cell.control_raw)}（双击查看样本证据）`"
        @click="emit('select', { pair, cell })"
        @dblclick="emit('openEvidence', { pair, cell })"
      >
        <span class="cell-label">{{ cell.label }}</span>
        <span class="cell-value">{{ cell.display }}</span>
        <span class="cell-hint">{{ cellHint(cell) }}</span>
      </button>
    </div>
  </article>
</template>

<script setup lang="ts">
import { displayKind, displayRaw, rowStateLabel } from './format'
import type { Cell, Pair } from './types'

defineProps<{
  pairs: Pair[]
  selectedCellId: string | null
}>()

const emit = defineEmits<{
  (event: 'select', payload: { pair: Pair; cell: Cell }): void
  (event: 'openEvidence', payload: { pair: Pair; cell: Cell }): void
}>()

function rowTone(state: string) {
  if (state === 'paired') return 'ok'
  if (state === 'missing_base') return 'warn'
  return 'danger'
}

function cellHint(cell: Cell) {
  if (cell.status === 'missing') return '仅一侧存在'
  if (cell.status === 'null') return cell.null_note ?? displayKind(cell.base_kind)
  if (cell.status === 'diff') return `超阈值（阈值 ${cell.threshold}）`
  if (cell.diff !== null) return `阈值内（阈值 ${cell.threshold}）`
  return '一致'
}
</script>
