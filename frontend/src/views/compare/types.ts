/** 对比分析差异矩阵的前后端数据结构。字段名与后端 JSON 一一对应。 */

export type DatasetField = { name: string; label: string; type: string }

export type DatasetBrief = {
  id?: number
  code: string
  name: string
  source_table: string
  status: string
  fields: DatasetField[]
}

export type KeyPair = { base: string; control: string; label: string }

export type ValueField = {
  base: string
  control: string
  label: string
  threshold: number
  threshold_mode: string
}

export type Mapping = { business_keys: KeyPair[]; value_fields: ValueField[] }

export type MappingDetail = {
  plan_id: number
  plan_no: string
  base_dataset: DatasetBrief
  control_dataset: DatasetBrief
  mapping: Mapping
  mapping_source: string
  validation: string[]
  thresholds: Record<string, { threshold: number; mode: string; base: string; control: string }>
}

export type SideIdentity = {
  role: string
  code: string
  name: string
  source_table: string
  status_at_seal: string
  digest: string
  record_count: number
}

export type RoundSnapshot = {
  plan_id: number
  plan_no: string
  round_no: number
  sealed_at: string
  diff_direction: string
  digest: string
  swap_of: number | null
  base: SideIdentity
  control: SideIdentity
  mapping: Mapping
  thresholds: Record<string, { threshold: number; mode: string; base: string; control: string }>
}

export type RoundSummary = {
  pair_count: number
  matched_pairs: number
  missing_base_pairs: number
  missing_control_pairs: number
  adjudicated_pairs: number
  cell_count: number
  diff_cells: number
  within_cells: number
  missing_cells: number
  null_cells: number
  quarantine_groups: number
  unresolved_quarantine_groups: number
  quarantined_rows: number
  base_records: number
  control_records: number
}

export type SignedInfo = {
  at: string
  note: string
  snapshot_digest: string
  summary: RoundSummary
}

export type RoundBrief = {
  id: number
  plan_id: number
  plan_no: string
  round_no: number
  status: string
  created_at: string
  completed_at: string | null
  signed: SignedInfo | null
  snapshot: RoundSnapshot
  mapping: Mapping
  thresholds: Record<string, { threshold: number; mode: string; base: string; control: string }>
  summary: RoundSummary
  source_counts: Record<string, number>
  block_reasons: string[]
  warnings: string[]
  matrix_revision: number
  swap_of: number | null
  parent_round_id: number | null
  unresolved_groups: number
  status_history: { status: string; at: string; note: string }[]
  pairs_total: number
}

export type RecordValues = { record_id: string; values: Record<string, unknown> }

export type Cell = {
  cell_id: string
  field_index: number
  label: string
  base_field: string
  control_field: string
  base_raw: unknown
  control_raw: unknown
  base_kind: string
  control_kind: string
  threshold: number
  threshold_mode: string
  diff: number | null
  abs_diff: number | null
  within_threshold: boolean | null
  display: string
  status: 'diff' | 'within' | 'missing' | 'null'
  state_detail: string
  null_note: string | null
}

export type Pair = {
  pair_id: string
  key: string
  key_values: unknown[]
  row_state: string
  match_basis: string
  base_record_id: string | null
  control_record_id: string | null
  base_record: RecordValues | null
  control_record: RecordValues | null
  ignored_base_record_ids: string[]
  ignored_control_record_ids: string[]
  cells: Cell[]
  adjudicated?: boolean
}

export type QuarantineGroup = {
  group_id: string
  key: string
  key_values: unknown[]
  reason: string
  base_record_ids: string[]
  control_record_ids: string[]
  base_records: RecordValues[]
  control_records: RecordValues[]
  resolution: {
    decision: string
    at: string
    note: string
    base_record_id: string | null
    control_record_id: string | null
    ignored_base_record_ids?: string[]
    ignored_control_record_ids?: string[]
  } | null
}

export type RoundDetail = RoundBrief & {
  quarantine_groups: QuarantineGroup[]
  blockers: string[]
  definition_warnings: string[]
}

export type MatrixPage = {
  round_id: number
  round_no: number
  status: string
  matrix_revision: number
  snapshot: RoundSnapshot
  columns: { label: string; base: string; control: string; threshold: number | null }[]
  items: Pair[]
  total: number
  page: number
  size: number
  summary: RoundSummary
  legend: { state: string; label: string }[]
}

export type QueryEvidence = {
  id: number
  statement_no: string
  expression: string
  target_dataset: string
  status: string
}

export type CellEvidence = {
  round_id: number
  round_no: number
  cell_id: string
  key: string
  match_basis: string
  cell: Cell
  base: {
    role: string
    dataset_code: string
    dataset_name: string
    source_table: string
    record_id: string | null
    values: Record<string, unknown>
    present: boolean
    sealed_digest: string
  }
  control: {
    role: string
    dataset_code: string
    dataset_name: string
    source_table: string
    record_id: string | null
    values: Record<string, unknown>
    present: boolean
    sealed_digest: string
  }
  queries: { base: QueryEvidence | null; control: QueryEvidence | null }
  mapping: Mapping
  snapshot_digest: string
}

export type CellDetail = {
  round_id: number
  cell: Cell
  pair: Omit<Pair, 'cells'>
  trace: {
    pair_id: string
    key: string
    key_values: unknown[]
    row_state: string
    match_basis: string
    base_record_id: string | null
    control_record_id: string | null
    business_keys: KeyPair[]
    field_mapping: { base: string; control: string; label: string }
    threshold: number | null
    diff_direction: string
    base_kind: string | null
    control_kind: string | null
    sealed_at: string
    snapshot_digest: string
    round_no: number
    matrix_revision: number
    base_definition: SideIdentity
    control_definition: SideIdentity
    adjudicated: boolean
  }
  evidence_link: string
}
