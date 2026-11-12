"""对比分析接口：维护对比方案，覆盖提交校验、启用方案、停用方案等动作。

成对样本差异矩阵的接口也挂在这里：字段映射、比较轮次、隔离区裁决、逐格追溯。
注意路由顺序：静态子路径必须写在 /{entry_id} 之前，否则会被路径参数吃掉。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    CompareMappingPayload,
    CompareQuarantineResolution,
    CompareRoundCreate,
    CompareSignoff,
    EntryPayload,
    PageResult,
)
from app.services.compare import CompareService
from app.services.compare_matrix import compare_matrix_service

router = APIRouter(prefix="/api/compare", tags=["对比分析"])

service = CompareService()

LIST_FIELDS = ["方案编号", "基准数据集", "对照数据集", "对比维度", "对比指标", "差异阈值", "显著性水平", "输出展示"]
STATUSES = ["草稿", "待校验", "已启用", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按方案编号检索"),
    status: str | None = Query(default=None, description="草稿、待校验、已启用、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按方案编号与状态过滤对比分析列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出对比分析清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "compare", "total": total, "items": items}


# ---------------------------------------------------------------- 字段映射

@router.get("/plans/{plan_id}/mapping")
def get_mapping(plan_id: int) -> dict[str, Any]:
    """读取方案的字段映射建议、两侧数据集身份与校验结果。

    未登记映射时按字段标签推导，并明确标注来源，不静默假定。
    """
    detail, message = compare_matrix_service.mapping_detail(plan_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=message)
    return detail


@router.get("/mapping-preview")
def preview_mapping(
    base_dataset_code: str = Query(description="基准数据集编号"),
    control_dataset_code: str = Query(description="对照数据集编号"),
) -> dict[str, Any]:
    """从数据集管理选定的两个数据集推导字段映射，启动比较前先确认字段身份。"""
    detail, message = compare_matrix_service.preview_mapping(base_dataset_code, control_dataset_code)
    if detail is None:
        raise HTTPException(status_code=400, detail=message)
    return detail


@router.put("/plans/{plan_id}/mapping", response_model=ActionResult)
def save_mapping(plan_id: int, payload: CompareMappingPayload) -> ActionResult:
    """把确认过的字段映射登记回方案；字段不存在或缺业务键都会被拒绝并说明原因。"""
    entry, message = compare_matrix_service.replace_mapping(
        plan_id,
        payload.mapping,
        base_dataset_code=payload.base_dataset_code,
        control_dataset_code=payload.control_dataset_code,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="字段映射已登记，后续比较轮次沿用该字段身份", entry=entry)


# ---------------------------------------------------------------- 比较轮次

@router.get("/plans/{plan_id}/rounds")
def list_rounds(plan_id: int) -> dict[str, Any]:
    """列出一个方案下的全部比较轮次；重算与左右交换各自独立成轮，旧轮次保留快照。"""
    items, message = compare_matrix_service.list_rounds(plan_id)
    if not items and message:
        raise HTTPException(status_code=404, detail=message)
    return {"items": items, "total": len(items)}


@router.post("/plans/{plan_id}/rounds", response_model=ActionResult)
def create_round(plan_id: int, payload: CompareRoundCreate) -> ActionResult:
    """启动比较：封存两侧数据集定义、字段映射与阈值，计算期间任何一侧废弃都会阻断。"""
    entry, message = compare_matrix_service.create_round(
        plan_id,
        mapping=payload.mapping,
        base_dataset_code=payload.base_dataset_code,
        control_dataset_code=payload.control_dataset_code,
        parent_round_id=payload.parent_round_id,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"比较轮次 {entry['round_no']} 已启动，两侧定义已封存", entry=entry)


@router.get("/rounds/{round_id}")
def get_round(round_id: int) -> dict[str, Any]:
    """读取某个轮次的元数据、快照、隔离区与签认阻断原因。"""
    detail, message = compare_matrix_service.get_round(round_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=message)
    return detail


@router.post("/rounds/{round_id}/complete", response_model=ActionResult)
def complete_round(round_id: int) -> ActionResult:
    """完成计算并生成矩阵；计算期间封存对象被废弃时轮次转入已阻断并说明原因。"""
    entry, message = compare_matrix_service.complete_round(round_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="矩阵已生成", entry=entry)


@router.get("/rounds/{round_id}/matrix")
def get_matrix(
    round_id: int,
    page: int = 1,
    size: int = 20,
    state: str = Query(default="all", description="all、diff、missing、null"),
    keyword: str | None = Query(default=None, description="按业务键或记录编号检索"),
) -> dict[str, Any]:
    """分页读取差异矩阵；大结果集只返回当前页，配合前端分页按需加载。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    payload, message = compare_matrix_service.matrix_page(
        round_id, page=page, size=size, state=state, keyword=keyword,
    )
    if payload is None:
        raise HTTPException(status_code=409, detail=message)
    return payload


@router.get("/rounds/{round_id}/cells/{cell_id}")
def get_cell(round_id: int, cell_id: str) -> dict[str, Any]:
    """逐格追溯：字段映射、业务键、匹配依据、阈值与封存摘要都随格子返回。"""
    detail, message = compare_matrix_service.cell_detail(round_id, cell_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=message)
    return detail


@router.get("/rounds/{round_id}/cells/{cell_id}/evidence")
def get_cell_evidence(round_id: int, cell_id: str) -> dict[str, Any]:
    """样本证据：返回两侧原始记录与对应交互查询语句，供双击格子跨模块查看。"""
    detail, message = compare_matrix_service.cell_evidence(round_id, cell_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=message)
    return detail


@router.post("/rounds/{round_id}/quarantine/{group_id}", response_model=ActionResult)
def resolve_quarantine(round_id: int, group_id: str, payload: CompareQuarantineResolution) -> ActionResult:
    """裁决隔离键组：确认配对必须显式指定两侧记录，或整组不比较；不接受按顺序自动配对。"""
    entry, message = compare_matrix_service.resolve_quarantine(
        round_id,
        group_id,
        decision=payload.decision,
        base_record_id=payload.base_record_id,
        control_record_id=payload.control_record_id,
        note=payload.note,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"隔离键组 {group_id} 已裁决", entry=entry)


@router.post("/rounds/{round_id}/swap", response_model=ActionResult)
def swap_round(round_id: int) -> ActionResult:
    """左右交换：生成独立轮次，字段身份随角色互换，差值方向取反。"""
    entry, message = compare_matrix_service.swap_round(round_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"已生成左右交换轮次 {entry['round_no']}，差值方向相反", entry=entry)


@router.post("/rounds/{round_id}/signoff", response_model=ActionResult)
def signoff_round(round_id: int, payload: CompareSignoff) -> ActionResult:
    """签认结论；存在废弃阻断或未裁决歧义键组时拒绝，并列出全部原因。"""
    entry, message = compare_matrix_service.signoff_round(round_id, payload.note)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="结论已签认，快照摘要已记录", entry=entry)


# ---------------------------------------------------------------- 方案明细与动作

@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条对比方案明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"对比方案 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条对比方案，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="对比方案已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条对比方案执行提交校验、启用方案、停用方案；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
