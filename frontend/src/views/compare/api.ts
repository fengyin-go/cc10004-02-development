import { request } from '@/api/client'

import type {
  CellDetail,
  CellEvidence,
  MappingDetail,
  MatrixPage,
  RoundBrief,
  RoundDetail,
} from './types'

export type ActionResult<T = unknown> = {
  ok: boolean
  message: string
  entry: T | null
}

/** 统一的错误提取：把后端 detail 或 ok=false 的 message 变成一句可读的话。 */
async function unwrap<T>(response: Response, fallback: string): Promise<T> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `${fallback}（HTTP ${response.status}）`
    throw new Error(detail)
  }
  return payload as T
}

export function mappingPreview(baseCode: string, controlCode: string): Promise<MappingDetail> {
  const query = new URLSearchParams({
    base_dataset_code: baseCode,
    control_dataset_code: controlCode,
  })
  return request(`/api/compare/mapping-preview?${query.toString()}`).then((response) =>
    unwrap<MappingDetail>(response, '字段映射推导失败'),
  )
}

/** 读取方案已登记的字段映射（含两侧数据集身份）；未登记时后端按字段标签推导。 */
export function mappingPreviewByPlan(planId: number): Promise<MappingDetail> {
  return request(`/api/compare/plans/${planId}/mapping`).then((response) =>
    unwrap<MappingDetail>(response, '字段映射读取失败'),
  )
}

export function saveMapping(
  planId: number,
  baseCode: string,
  controlCode: string,
  mapping: MappingDetail['mapping'],
): Promise<ActionResult> {
  return request(`/api/compare/plans/${planId}/mapping`, {
    method: 'PUT',
    body: JSON.stringify({
      base_dataset_code: baseCode,
      control_dataset_code: controlCode,
      mapping,
    }),
  }).then((response) => unwrap<ActionResult>(response, '字段映射保存失败'))
}

export function createRound(planId: number, parentRoundId: number | null = null): Promise<ActionResult> {
  return request(`/api/compare/plans/${planId}/rounds`, {
    method: 'POST',
    body: JSON.stringify(parentRoundId ? { parent_round_id: parentRoundId } : {}),
  }).then((response) => unwrap<ActionResult>(response, '启动比较失败'))
}

export function fetchRounds(planId: number): Promise<{ items: RoundBrief[]; total: number }> {
  return request(`/api/compare/plans/${planId}/rounds`).then((response) =>
    unwrap<{ items: RoundBrief[]; total: number }>(response, '比较轮次读取失败'),
  )
}

export function fetchRound(roundId: number): Promise<RoundDetail> {
  return request(`/api/compare/rounds/${roundId}`).then((response) =>
    unwrap<RoundDetail>(response, '轮次明细读取失败'),
  )
}

export function completeRound(roundId: number): Promise<ActionResult> {
  return request(`/api/compare/rounds/${roundId}/complete`, { method: 'POST' }).then((response) =>
    unwrap<ActionResult>(response, '矩阵计算失败'),
  )
}

export function fetchMatrix(
  roundId: number,
  options: { page: number; size: number; state: string; keyword: string },
): Promise<MatrixPage> {
  const query = new URLSearchParams({
    page: String(options.page),
    size: String(options.size),
    state: options.state,
  })
  if (options.keyword.trim()) query.set('keyword', options.keyword.trim())
  return request(`/api/compare/rounds/${roundId}/matrix?${query.toString()}`).then((response) =>
    unwrap<MatrixPage>(response, '矩阵取数失败'),
  )
}

export function fetchCellEvidence(roundId: number, cellId: string): Promise<CellEvidence> {
  return request(`/api/compare/rounds/${roundId}/cells/${encodeURIComponent(cellId)}/evidence`).then(
    (response) => unwrap<CellEvidence>(response, '样本证据读取失败'),
  )
}

export function fetchCellDetail(roundId: number, cellId: string): Promise<CellDetail> {
  return request(`/api/compare/rounds/${roundId}/cells/${encodeURIComponent(cellId)}`).then(
    (response) => unwrap<CellDetail>(response, '格子追溯信息读取失败'),
  )
}

export function resolveQuarantine(
  roundId: number,
  groupId: string,
  body: { decision: string; base_record_id?: string; control_record_id?: string; note?: string },
): Promise<ActionResult> {
  return request(`/api/compare/rounds/${roundId}/quarantine/${groupId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  }).then((response) => unwrap<ActionResult>(response, '隔离区裁决失败'))
}

export function swapRound(roundId: number): Promise<ActionResult> {
  return request(`/api/compare/rounds/${roundId}/swap`, { method: 'POST' }).then((response) =>
    unwrap<ActionResult>(response, '左右交换失败'),
  )
}

export function signoffRound(roundId: number, note: string): Promise<ActionResult> {
  return request(`/api/compare/rounds/${roundId}/signoff`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  }).then((response) => unwrap<ActionResult>(response, '结论签认失败'))
}
