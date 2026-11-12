"""成对样本差异矩阵：封存字段身份、业务键配对、隔离区裁决与逐格追溯。

设计取舍：
- 比较轮次是独立不可变快照：启动时封存两侧数据集定义、字段映射、阈值；
  重算或左右交换都会生成新的轮次，旧轮次的矩阵仍保留当时的字段身份与阈值。
- 配对只认业务键。某一侧同键多行即判定为歧义键组，整组进入隔离区，
  不按输入顺序强行配对；确认配对必须由人显式指定两侧记录。
- 单元格状态区分：数值差（超阈值/阈值内）、缺行、空值（含空字符串与 None），
  空字符串不会折算成数字 0。
- 计算期间任一侧数据集被废弃，轮次转为已阻断，签认结论被拒绝。
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any

from app.sample_data import records_for_dataset
from app.store import store

PLAN_MODULE = "compare"
DATASTORE_MODULE = "datastore"

ROUND_COMPUTING = "计算中"
ROUND_COMPLETE = "计算完成"
ROUND_BLOCKED = "已阻断"
ROUND_SIGNED = "已签认"

SIDE_BASE = "基准"
SIDE_CONTROL = "对照"

BLANK_KINDS = {"null", "blank"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def _dataset_by_code(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    for row in store.rows(DATASTORE_MODULE):
        if str(row.get("数据集编号") or "") == str(code):
            return row
    return None


def _dataset_by_name(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    for row in store.rows(DATASTORE_MODULE):
        if str(row.get("数据集名称") or "") == str(name):
            return row
    return None


def dataset_fields(dataset: dict[str, Any]) -> list[dict[str, str]]:
    """读取数据集字段定义；旧数据只有“字段列表”文本时按 a(标签) 形式解析。"""
    raw = dataset.get("字段定义")
    if isinstance(raw, list) and raw:
        fields: list[dict[str, str]] = []
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                fields.append({
                    "name": str(item["name"]),
                    "label": str(item.get("label") or item["name"]),
                    "type": str(item.get("type") or "string"),
                })
        if fields:
            return fields
    parsed: list[dict[str, str]] = []
    for chunk in str(dataset.get("字段列表") or "").split(","):
        text = chunk.strip()
        if not text:
            continue
        if "(" in text and text.endswith(")"):
            name, label = text.split("(", 1)
            parsed.append({"name": name.strip(), "label": label[:-1].strip(), "type": "string"})
        else:
            parsed.append({"name": text, "label": text, "type": "string"})
    return parsed


def _field_map(dataset: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {field["name"]: field for field in dataset_fields(dataset)}


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def value_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str) and value.strip() == "":
        return "blank"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        try:
            float(value.strip())
        except ValueError:
            return "text"
        return "number"
    return "text"


def numeric_value(value: Any) -> float | None:
    """只有真正是数值或数值字符串才折算；空字符串、None 一律不折算为 0。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _key_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm_key(values: list[Any]) -> str:
    return "\u0001".join(_key_text(value) for value in values)


def _is_within(diff: float, threshold: float) -> bool:
    return abs(diff) <= threshold + 1e-9


def _round_num(value: float) -> float:
    return round(value, 6)


class CompareMatrixService:
    """比较轮次与矩阵的唯一入口；状态流转只在这里发生。"""

    def __init__(self) -> None:
        self._rounds: dict[int, dict[str, Any]] = {}
        self._next_round_id = 1
        self._round_seq: dict[int, int] = {}

    # ------------------------------------------------------------------ 方案与映射

    def mapping_detail(self, plan_id: int) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(PLAN_MODULE, plan_id)
        if plan is None:
            return None, f"对比方案 {plan_id} 不存在或已归档"
        base = _resolve_side_dataset(plan, base=True)
        control = _resolve_side_dataset(plan, base=False)
        if base is None or control is None:
            return None, "基准或对照数据集未在上游数据集管理中登记，无法确定字段映射"
        mapping = copy.deepcopy(plan.get("字段映射")) if plan.get("字段映射") else _derive_mapping(plan, base, control)
        warnings = _validate_mapping(mapping, base, control)
        return {
            "plan_id": plan_id,
            "plan_no": plan.get("方案编号"),
            "base_dataset": _dataset_brief(base),
            "control_dataset": _dataset_brief(control),
            "mapping": mapping,
            "mapping_source": "方案已登记字段映射" if plan.get("字段映射") else "按数据集字段标签自动推导",
            "validation": warnings,
            "thresholds": _thresholds(mapping),
        }, ""

    # ------------------------------------------------------------------ 轮次生命周期

    def create_round(
        self,
        plan_id: int,
        *,
        mapping: dict[str, Any] | None = None,
        base_dataset_code: str | None = None,
        control_dataset_code: str | None = None,
        parent_round_id: int | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(PLAN_MODULE, plan_id)
        if plan is None:
            return None, f"对比方案 {plan_id} 不存在或已归档"
        if parent_round_id is not None:
            parent = self._rounds.get(parent_round_id)
            if parent is None:
                return None, f"重算来源轮次 {parent_round_id} 不存在"
            if int(parent["plan_id"]) != plan_id:
                return None, f"重算来源轮次 {parent_round_id} 不属于对比方案 {plan_id}"
        base = _dataset_by_code(base_dataset_code) or _resolve_side_dataset(plan, base=True)
        control = _dataset_by_code(control_dataset_code) or _resolve_side_dataset(plan, base=False)
        if base is None or control is None:
            return None, "基准或对照数据集缺失，无法启动比较"
        for role, dataset in ((SIDE_BASE, base), (SIDE_CONTROL, control)):
            if dataset.get("status") != "已生效":
                return None, (
                    f"{role}数据集「{dataset.get('数据集名称')}」当前状态为"
                    f"「{dataset.get('status')}」，未生效，不能启动比较"
                )
        effective_mapping = copy.deepcopy(mapping) if mapping else copy.deepcopy(plan.get("字段映射"))
        if not effective_mapping:
            effective_mapping = _derive_mapping(plan, base, control)
        problems = _mapping_problems(effective_mapping, base, control)
        if problems:
            return None, "字段映射不成立：" + "；".join(problems)

        round_id = self._next_round_id
        self._next_round_id += 1
        seq = self._round_seq.get(plan_id, 0) + 1
        self._round_seq[plan_id] = seq
        sealed_at = _now()
        snapshot = {
            "plan_id": plan_id,
            "plan_no": plan.get("方案编号"),
            "round_no": seq,
            "sealed_at": sealed_at,
            "direction": "base→control",
            "diff_direction": "对照 - 基准",
            "mapping": effective_mapping,
            "thresholds": _thresholds(effective_mapping),
            "base": _seal_dataset(base, SIDE_BASE),
            "control": _seal_dataset(control, SIDE_CONTROL),
        }
        snapshot["digest"] = _digest({
            "mapping": effective_mapping,
            "base": {k: snapshot["base"].get(k) for k in ("code", "name", "source_table", "status_at_seal", "fields")},
            "control": {k: snapshot["control"].get(k) for k in ("code", "name", "source_table", "status_at_seal", "fields")},
        })
        entry = {
            "id": round_id,
            "plan_id": plan_id,
            "plan_no": plan.get("方案编号"),
            "round_no": seq,
            "status": ROUND_COMPUTING,
            "status_history": [{"status": ROUND_COMPUTING, "at": sealed_at, "note": "已封存两侧定义，等待完成计算"}],
            "snapshot": snapshot,
            "created_at": sealed_at,
            "completed_at": None,
            "signed": None,
            "block_reasons": [],
            "warnings": [],
            "pairs": [],
            "quarantine_groups": [],
            "summary": {},
            "source_counts": {},
            "parent_round_id": parent_round_id,
            "swap_of": None,
            "matrix_revision": 0,
        }
        self._rounds[round_id] = entry
        return self._round_brief(entry), ""

    def preview_mapping(self, base_code: str, control_code: str) -> tuple[dict[str, Any] | None, str]:
        """从数据集管理里选定的两个数据集推导字段映射，供启动比较前确认。"""
        base = _dataset_by_code(base_code)
        control = _dataset_by_code(control_code)
        if base is None:
            return None, f"基准数据集 {base_code} 不在数据集管理中"
        if control is None:
            return None, f"对照数据集 {control_code} 不在数据集管理中"
        if base_code == control_code:
            return None, "基准与对照不能选择同一个数据集"
        mapping = _derive_mapping({}, base, control)
        return {
            "base_dataset": _dataset_brief(base),
            "control_dataset": _dataset_brief(control),
            "mapping": mapping,
            "mapping_source": "按数据集字段标签自动推导，需人工确认",
            "validation": _mapping_problems(mapping, base, control),
            "thresholds": _thresholds(mapping),
        }, ""

    def replace_mapping(
        self,
        plan_id: int,
        mapping: dict[str, Any],
        *,
        base_dataset_code: str | None = None,
        control_dataset_code: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """把前端确认过的字段映射登记回方案，后续轮次沿用同一份字段身份。

        同时把方案里的基准/对照数据集指向数据集管理中确认过的那两条，避免两处口径不一致。
        """
        plan = store.find(PLAN_MODULE, plan_id)
        if plan is None:
            return None, f"对比方案 {plan_id} 不存在或已归档"
        base = _dataset_by_code(base_dataset_code) or _resolve_side_dataset(plan, base=True)
        control = _dataset_by_code(control_dataset_code) or _resolve_side_dataset(plan, base=False)
        if base is None or control is None:
            return None, "基准或对照数据集缺失，无法保存字段映射"
        if str(base.get("数据集编号")) == str(control.get("数据集编号")):
            return None, "基准与对照不能使用同一个数据集"
        problems = _mapping_problems(mapping, base, control)
        if problems:
            return None, "字段映射不成立：" + "；".join(problems)
        plan["字段映射"] = copy.deepcopy(mapping)
        plan["基线数据集编号"] = base.get("数据集编号")
        plan["基准数据集"] = base.get("数据集名称")
        plan["对照数据集编号"] = control.get("数据集编号")
        plan["对照数据集"] = control.get("数据集名称")
        return copy.deepcopy(plan), ""

    def complete_round(self, round_id: int) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        if entry["status"] != ROUND_COMPUTING:
            return None, f"比较轮次 {round_id} 当前状态为「{entry['status']}」，不能重复计算"
        at = _now()
        snapshot = entry["snapshot"]
        block_reasons = _deprecation_blockers(snapshot)
        warnings = _definition_warnings(snapshot)
        pairs, groups, counts = self._build_pairs(snapshot)
        entry["pairs"] = pairs
        entry["quarantine_groups"] = groups
        entry["source_counts"] = counts
        entry["completed_at"] = at
        entry["warnings"] = warnings
        entry["matrix_revision"] = 1
        if block_reasons:
            entry["status"] = ROUND_BLOCKED
            entry["block_reasons"] = block_reasons
            entry["status_history"].append({
                "status": ROUND_BLOCKED,
                "at": at,
                "note": "计算期间封存对象被废弃，矩阵保留但结论签认被阻止",
            })
            entry["summary"] = self._summarize(entry)
            return self._round_brief(entry), ""
        entry["status"] = ROUND_COMPLETE
        entry["status_history"].append({"status": ROUND_COMPLETE, "at": at, "note": "矩阵计算完成"})
        entry["summary"] = self._summarize(entry)
        return self._round_brief(entry), ""

    def signoff_round(self, round_id: int, note: str | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        if entry["status"] == ROUND_SIGNED:
            return None, f"比较轮次 {round_id} 已签认，不能重复签认"
        if entry["status"] == ROUND_COMPUTING:
            return None, f"比较轮次 {round_id} 尚未完成计算，不能签认"
        blockers = list(_deprecation_blockers(entry["snapshot"]))
        unresolved = [group for group in entry["quarantine_groups"] if not group.get("resolution")]
        if unresolved:
            keys = "、".join(str(group.get("key") or "空业务键") for group in unresolved[:5])
            blockers.append(
                f"{len(unresolved)} 个歧义键组尚未裁决（如 {keys}），不能签认结论；"
                "歧义键组必须逐组裁决后才能签认"
            )
        if blockers:
            blockers = list(dict.fromkeys(blockers))
            # 只有封存对象失效这类结构性问题才把轮次转为已阻断；
            # 隔离区未裁决只是暂时拒绝签认，轮次仍保持计算完成，裁决后可以重新签认。
            if entry["status"] == ROUND_COMPLETE and _deprecation_blockers(entry["snapshot"]):
                entry["status"] = ROUND_BLOCKED
                entry["status_history"].append({
                    "status": ROUND_BLOCKED, "at": _now(), "note": "签认前复核未通过，转已阻断",
                })
                blockers = list(dict.fromkeys([*(entry.get("block_reasons") or []), *blockers]))
                entry["block_reasons"] = blockers
            entry["summary"] = self._summarize(entry)
            return None, "；".join(blockers)
        at = _now()
        entry["status"] = ROUND_SIGNED
        entry["signed"] = {
            "at": at,
            "note": (note or "").strip() or "结论已签认",
            "snapshot_digest": entry["snapshot"].get("digest"),
            "summary": entry["summary"],
        }
        entry["status_history"].append({"status": ROUND_SIGNED, "at": at, "note": entry["signed"]["note"]})
        return self._round_brief(entry), ""

    def swap_round(self, round_id: int) -> tuple[dict[str, Any] | None, str]:
        """左右交换：生成独立轮次，字段身份随角色互换，差值方向取反。"""
        source = self._rounds.get(round_id)
        if source is None:
            return None, f"比较轮次 {round_id} 不存在"
        if source["status"] not in (ROUND_COMPLETE, ROUND_BLOCKED, ROUND_SIGNED):
            return None, f"比较轮次 {round_id} 尚未完成计算，不能交换左右"
        snapshot = source["snapshot"]
        swapped_mapping = _swap_mapping(snapshot["mapping"])
        plan = store.find(PLAN_MODULE, int(snapshot["plan_id"]))
        if plan is None:
            return None, "原对比方案不存在或已归档"
        # 交换后的基准来自原对照、对照来自原基准；每个字段仍指向原来的物理字段。
        new_entry, message = self.create_round(
            int(snapshot["plan_id"]),
            mapping=swapped_mapping,
            base_dataset_code=snapshot["control"]["code"],
            control_dataset_code=snapshot["base"]["code"],
        )
        if new_entry is None:
            return None, message
        target = self._rounds[int(new_entry["id"])]
        target["swap_of"] = round_id
        target["snapshot"]["swap_of"] = round_id
        target["snapshot"]["diff_direction"] = "对照 - 基准（左右已交换）"
        target["snapshot"]["digest"] = _digest({
            "swap_of": round_id,
            "mapping": target["snapshot"]["mapping"],
            "base": target["snapshot"]["base"]["code"],
            "control": target["snapshot"]["control"]["code"],
        })
        target["status_history"].append({
            "status": ROUND_COMPUTING, "at": _now(),
            "note": f"由轮次 {round_id} 左右交换生成，差值方向相反",
        })
        return self._round_brief(target), ""

    def resolve_quarantine(
        self,
        round_id: int,
        group_id: str,
        *,
        decision: str,
        base_record_id: str | None,
        control_record_id: str | None,
        note: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        if entry["status"] == ROUND_SIGNED:
            return None, "轮次已签认，隔离区不可再变更"
        group = next((item for item in entry["quarantine_groups"] if item.get("group_id") == group_id), None)
        if group is None:
            return None, f"隔离键组 {group_id} 不存在"
        if group.get("resolution"):
            return None, f"隔离键组 {group_id} 已经裁决，不能重复提交"
        decision_text = (decision or "").strip()
        if decision_text not in ("确认配对", "整组不比较"):
            return None, "裁决动作只能是「确认配对」或「整组不比较」"
        at = _now()
        if decision_text == "整组不比较":
            group["resolution"] = {
                "decision": decision_text, "at": at,
                "note": (note or "").strip() or "人工确认整组不参与比较",
                "base_record_id": None, "control_record_id": None,
            }
        else:
            base_options = {row["record_id"]: row for row in group["base_records"]}
            control_options = {row["record_id"]: row for row in group["control_records"]}
            # 有记录的一侧都必须显式指定；另一侧整侧缺行时允许只选单侧，作为缺行配对入矩阵。
            if base_options and (not base_record_id or base_record_id not in base_options):
                return None, "确认配对必须显式选择该键组基准侧的一条记录"
            if control_options and (not control_record_id or control_record_id not in control_options):
                return None, "确认配对必须显式选择该键组对照侧的一条记录"
            if not base_options and not control_options:
                return None, "该键组两侧都没有可配对记录，请整组不比较"
            pair = self._build_pair(
                entry["snapshot"],
                group["key"],
                group.get("key_values") or [],
                [base_options[base_record_id]] if base_record_id else [],
                [control_options[control_record_id]] if control_record_id else [],
                "人工裁决确认",
                ignored={
                    "base": [rid for rid in base_options if rid != base_record_id],
                    "control": [rid for rid in control_options if rid != control_record_id],
                },
            )
            pair["adjudicated"] = True
            _assign_pair_id(entry["pairs"], pair)
            entry["pairs"].append(pair)
            group["resolution"] = {
                "decision": decision_text, "at": at,
                "note": (note or "").strip() or "人工确认配对",
                "base_record_id": base_record_id, "control_record_id": control_record_id,
                "ignored_base_record_ids": pair.get("ignored_base_record_ids", []),
                "ignored_control_record_ids": pair.get("ignored_control_record_ids", []),
            }
        entry["matrix_revision"] = int(entry.get("matrix_revision") or 0) + 1
        entry["summary"] = self._summarize(entry)
        return self._round_brief(entry), ""

    # ------------------------------------------------------------------ 查询

    def list_rounds(self, plan_id: int) -> tuple[list[dict[str, Any]], str]:
        if store.find(PLAN_MODULE, plan_id) is None:
            return [], f"对比方案 {plan_id} 不存在或已归档"
        items = [self._round_brief(entry) for entry in self._rounds.values() if int(entry["plan_id"]) == plan_id]
        items.sort(key=lambda item: int(item["id"]), reverse=True)
        return items, ""

    def get_round(self, round_id: int) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        detail = self._round_brief(entry)
        detail["quarantine_groups"] = copy.deepcopy(entry["quarantine_groups"])
        detail["blockers"] = self._signoff_blockers(entry)
        detail["definition_warnings"] = entry.get("warnings") or []
        return detail, ""

    def matrix_page(
        self,
        round_id: int,
        *,
        page: int = 1,
        size: int = 20,
        state: str = "all",
        keyword: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        if not entry.get("pairs"):
            return None, f"比较轮次 {round_id} 尚未完成计算，矩阵不可见"
        rows = entry["pairs"]
        if state == "diff":
            rows = [pair for pair in rows if _pair_has(pair, "diff")]
        elif state == "missing":
            rows = [pair for pair in rows if pair["row_state"] != "paired"]
        elif state == "null":
            rows = [pair for pair in rows if _pair_has(pair, "null")]
        elif state != "all":
            return None, "矩阵筛选只支持 all、diff、missing、null"
        if keyword:
            needle = keyword.strip().lower()
            rows = [
                pair for pair in rows
                if needle in str(pair.get("key") or "").lower()
                or needle in str(pair.get("base_record_id") or "").lower()
                or needle in str(pair.get("control_record_id") or "").lower()
            ]
        total = len(rows)
        start = max(page - 1, 0) * size
        items = copy.deepcopy(rows[start:start + size])
        return {
            "round_id": round_id,
            "round_no": entry["round_no"],
            "status": entry["status"],
            "matrix_revision": entry["matrix_revision"],
            "snapshot": _snapshot_brief(entry["snapshot"]),
            "columns": [
                {
                    "label": item.get("label"),
                    "base": item.get("base"),
                    "control": item.get("control"),
                    "threshold": item.get("threshold"),
                }
                for item in entry["snapshot"]["mapping"]["value_fields"]
            ],
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "summary": entry["summary"],
            "legend": [
                {"state": "diff", "label": "数值差（超出阈值）"},
                {"state": "within", "label": "阈值内 / 一致"},
                {"state": "missing", "label": "缺行（仅一侧存在）"},
                {"state": "null", "label": "空值（空字符串或缺失，不等同 0）"},
            ],
        }, ""

    def cell_detail(self, round_id: int, cell_id: str) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        pair, cell = _locate_cell(entry, cell_id)
        if pair is None or cell is None:
            return None, f"矩阵格子 {cell_id} 不存在于轮次 {round_id}"
        trace = {
            "pair_id": pair["pair_id"],
            "key": pair["key"],
            "key_values": pair.get("key_values") or [],
            "row_state": pair["row_state"],
            "match_basis": pair["match_basis"],
            "base_record_id": pair.get("base_record_id"),
            "control_record_id": pair.get("control_record_id"),
            "business_keys": entry["snapshot"]["mapping"]["business_keys"],
            "field_mapping": {
                "base": cell["base_field"],
                "control": cell["control_field"],
                "label": cell["label"],
            },
            "threshold": cell.get("threshold"),
            "diff_direction": entry["snapshot"].get("diff_direction", "对照 - 基准"),
            "base_kind": cell.get("base_kind"),
            "control_kind": cell.get("control_kind"),
            "sealed_at": entry["snapshot"]["sealed_at"],
            "snapshot_digest": entry["snapshot"].get("digest"),
            "round_no": entry["round_no"],
            "matrix_revision": entry["matrix_revision"],
            "base_definition": _side_identity(entry["snapshot"]["base"]),
            "control_definition": _side_identity(entry["snapshot"]["control"]),
            "adjudicated": bool(pair.get("adjudicated")),
        }
        return {
            "round_id": round_id,
            "cell": copy.deepcopy(cell),
            "pair": {key: copy.deepcopy(value) for key, value in pair.items() if key != "cells"},
            "trace": trace,
            "evidence_link": f"/api/compare/rounds/{round_id}/cells/{cell_id}/evidence",
        }, ""

    def cell_evidence(self, round_id: int, cell_id: str) -> tuple[dict[str, Any] | None, str]:
        entry = self._rounds.get(round_id)
        if entry is None:
            return None, f"比较轮次 {round_id} 不存在"
        pair, cell = _locate_cell(entry, cell_id)
        if pair is None or cell is None:
            return None, f"矩阵格子 {cell_id} 不存在于轮次 {round_id}"
        evidence = {
            "round_id": round_id,
            "round_no": entry["round_no"],
            "cell_id": cell_id,
            "key": pair["key"],
            "match_basis": pair["match_basis"],
            "cell": copy.deepcopy(cell),
            "base": _side_evidence(entry["snapshot"]["base"], pair.get("base_record_id"), pair.get("base_record")),
            "control": _side_evidence(entry["snapshot"]["control"], pair.get("control_record_id"), pair.get("control_record")),
            "queries": {
                "base": _query_for_dataset(entry["snapshot"]["base"]),
                "control": _query_for_dataset(entry["snapshot"]["control"]),
            },
            "mapping": entry["snapshot"]["mapping"],
            "snapshot_digest": entry["snapshot"].get("digest"),
        }
        return evidence, ""

    # ------------------------------------------------------------------ 内部实现

    def _round_brief(self, entry: dict[str, Any]) -> dict[str, Any]:
        snapshot = entry["snapshot"]
        return {
            "id": entry["id"],
            "plan_id": entry["plan_id"],
            "plan_no": entry["plan_no"],
            "round_no": entry["round_no"],
            "status": entry["status"],
            "created_at": entry["created_at"],
            "completed_at": entry["completed_at"],
            "signed": copy.deepcopy(entry["signed"]),
            "snapshot": _snapshot_brief(snapshot),
            "mapping": copy.deepcopy(snapshot["mapping"]),
            "thresholds": copy.deepcopy(snapshot.get("thresholds") or {}),
            "summary": copy.deepcopy(entry["summary"]),
            "source_counts": copy.deepcopy(entry["source_counts"]),
            "block_reasons": list(entry["block_reasons"]),
            "warnings": list(entry["warnings"]),
            "matrix_revision": entry["matrix_revision"],
            "swap_of": entry.get("swap_of"),
            "parent_round_id": entry.get("parent_round_id"),
            "unresolved_groups": sum(1 for group in entry["quarantine_groups"] if not group.get("resolution")),
            "status_history": copy.deepcopy(entry["status_history"]),
            "pairs_total": len(entry["pairs"]),
        }

    def _signoff_blockers(self, entry: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if entry["status"] == ROUND_SIGNED:
            return blockers
        if entry["status"] == ROUND_COMPUTING:
            blockers.append("轮次仍在计算中，尚未生成矩阵")
        blockers.extend(_deprecation_blockers(entry["snapshot"]))
        if entry.get("block_reasons"):
            blockers.extend(entry["block_reasons"])
        unresolved = [group for group in entry["quarantine_groups"] if not group.get("resolution")]
        if unresolved:
            blockers.append(
                f"{len(unresolved)} 个歧义键组尚未裁决（如 "
                f"{'、'.join(str(group.get('key') or '空业务键') for group in unresolved[:5])}）"
            )
        return list(dict.fromkeys(blockers))

    def _build_pairs(self, snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
        base_records = records_for_dataset(snapshot["base"]["code"])
        control_records = records_for_dataset(snapshot["control"]["code"])
        keys = snapshot["mapping"]["business_keys"]
        base_keys = [(record, [record["values"].get(item["base"]) for item in keys]) for record in base_records]
        control_keys = [(record, [record["values"].get(item["control"]) for item in keys]) for record in control_records]
        grouped_base: dict[str, list[dict[str, Any]]] = {}
        grouped_control: dict[str, list[dict[str, Any]]] = {}
        key_values: dict[str, list[Any]] = {}
        for record, raw_values in base_keys:
            key = _norm_key(raw_values)
            grouped_base.setdefault(key, []).append(record)
            key_values.setdefault(key, raw_values)
        for record, raw_values in control_keys:
            key = _norm_key(raw_values)
            grouped_control.setdefault(key, []).append(record)
            key_values.setdefault(key, raw_values)
        all_keys = sorted(grouped_base.keys() | grouped_control.keys())

        pairs: list[dict[str, Any]] = []
        groups: list[dict[str, Any]] = []
        for sequence, key in enumerate(all_keys, start=1):
            base_rows = grouped_base.get(key, [])
            control_rows = grouped_control.get(key, [])
            raw_values = key_values.get(key, [])
            if key == "" or len(base_rows) > 1 or len(control_rows) > 1:
                reasons: list[str] = []
                if key == "":
                    reasons.append("业务键为空")
                if len(base_rows) > 1:
                    reasons.append(f"基准侧同键 {len(base_rows)} 行")
                if len(control_rows) > 1:
                    reasons.append(f"对照侧同键 {len(control_rows)} 行")
                if not reasons:
                    reasons.append("业务键重复")
                groups.append({
                    "group_id": f"Q-{len(groups) + 1:02d}",
                    "key": key or "（空业务键）",
                    "key_values": raw_values,
                    "reason": "；".join(reasons),
                    "base_record_ids": [row["record_id"] for row in base_rows],
                    "control_record_ids": [row["record_id"] for row in control_rows],
                    "base_records": [_record_brief(row) for row in base_rows],
                    "control_records": [_record_brief(row) for row in control_rows],
                    "resolution": None,
                })
                continue
            if base_rows and control_rows:
                pair = self._build_pair(snapshot, key, raw_values, base_rows, control_rows,
                                        "业务键唯一匹配")
            elif base_rows:
                pair = self._build_pair(snapshot, key, raw_values, base_rows, [],
                                        "基准侧唯一，对照侧缺行")
            else:
                pair = self._build_pair(snapshot, key, raw_values, [], control_rows,
                                        "对照侧唯一，基准侧缺行")
            _assign_pair_id(pairs, pair)
            pairs.append(pair)
        counts = {
            "base_records": len(base_records),
            "control_records": len(control_records),
            "base_key_groups": len(grouped_base),
            "control_key_groups": len(grouped_control),
        }
        return pairs, groups, counts

    def _build_pair(
        self,
        snapshot: dict[str, Any],
        key: str,
        raw_values: list[Any],
        base_rows: list[dict[str, Any]],
        control_rows: list[dict[str, Any]],
        basis: str,
        *,
        ignored: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        base_row = base_rows[0] if base_rows else None
        control_row = control_rows[0] if control_rows else None
        if base_row and control_row:
            row_state = "paired"
        elif base_row:
            row_state = "missing_control"
        elif control_row:
            row_state = "missing_base"
        else:
            row_state = "paired"
        pair = {
            "pair_id": "",
            "key": key or "（空业务键）",
            "key_values": raw_values,
            "row_state": row_state,
            "match_basis": basis,
            "base_record_id": base_row["record_id"] if base_row else None,
            "control_record_id": control_row["record_id"] if control_row else None,
            "base_record": copy.deepcopy(base_row) if base_row else None,
            "control_record": copy.deepcopy(control_row) if control_row else None,
            "ignored_base_record_ids": list((ignored or {}).get("base") or []),
            "ignored_control_record_ids": list((ignored or {}).get("control") or []),
            "cells": [],
        }
        for index, field in enumerate(snapshot["mapping"]["value_fields"]):
            pair["cells"].append(self._build_cell(pair, field, index))
        return pair

    def _build_cell(self, pair: dict[str, Any], field: dict[str, Any], index: int) -> dict[str, Any]:
        base_raw = (pair["base_record"] or {}).get("values", {}).get(field["base"])
        control_raw = (pair["control_record"] or {}).get("values", {}).get(field["control"])
        base_kind = value_kind(base_raw) if pair["base_record"] else "missing"
        control_kind = value_kind(control_raw) if pair["control_record"] else "missing"
        threshold = float(field.get("threshold") or 0)
        mode = str(field.get("threshold_mode") or "absolute")
        cell: dict[str, Any] = {
            "cell_id": f"{pair['pair_id']}:{index}" if pair.get("pair_id") else f"pending:{index}",
            "field_index": index,
            "label": field.get("label") or field.get("base"),
            "base_field": field.get("base"),
            "control_field": field.get("control"),
            "base_raw": base_raw,
            "control_raw": control_raw,
            "base_kind": base_kind,
            "control_kind": control_kind,
            "threshold": threshold,
            "threshold_mode": mode,
            "diff": None,
            "abs_diff": None,
            "within_threshold": None,
            "display": "",
            "status": "within",
            "state_detail": "",
            "null_note": None,
        }
        if pair["row_state"] != "paired":
            cell.update({
                "status": "missing",
                "state_detail": pair["row_state"],
                "display": "缺行",
            })
            return cell
        if base_kind in BLANK_KINDS and control_kind in BLANK_KINDS:
            detail = "两侧空值"
            if "blank" in (base_kind, control_kind):
                detail = "两侧空值（含空字符串，不折算为 0）"
            cell.update({
                "status": "null",
                "state_detail": "both_blank",
                "display": "空值",
                "null_note": detail,
            })
            return cell
        if base_kind in BLANK_KINDS or control_kind in BLANK_KINDS:
            other_number = numeric_value(control_raw if base_kind in BLANK_KINDS else base_raw)
            note = "一侧为空值，另一侧为数值"
            if other_number == 0:
                note = "空字符串/空值与数字 0 不是同一取值"
            elif other_number is not None:
                note = f"一侧为空值，另一侧数值为 {other_number:g}"
            cell.update({
                "status": "null",
                "state_detail": "one_blank",
                "display": "空值×值",
                "null_note": note,
            })
            return cell
        if base_kind == "number" and control_kind == "number":
            base_number = numeric_value(base_raw)
            control_number = numeric_value(control_raw)
            assert base_number is not None and control_number is not None
            diff = _round_num(control_number - base_number)
            within = _is_within(diff, threshold)
            cell.update({
                "diff": diff,
                "abs_diff": _round_num(abs(diff)),
                "within_threshold": within,
                "status": "within" if within else "diff",
                "state_detail": "within_threshold" if within else "over_threshold",
                "display": ("+" if diff > 0 else "") + f"{diff:g}",
            })
            return cell
        base_text = str(base_raw).strip()
        control_text = str(control_raw).strip()
        if base_text == control_text:
            cell.update({
                "status": "within",
                "state_detail": "text_equal",
                "display": "一致",
                "within_threshold": True,
            })
        else:
            cell.update({
                "status": "diff",
                "state_detail": "text_diff",
                "display": f"{base_text}→{control_text}",
                "within_threshold": False,
            })
        return cell

    def _summarize(self, entry: dict[str, Any]) -> dict[str, Any]:
        pairs = entry.get("pairs") or []
        groups = entry.get("quarantine_groups") or []
        statuses: dict[str, int] = {"diff": 0, "within": 0, "missing": 0, "null": 0}
        for pair in pairs:
            for cell in pair["cells"]:
                statuses[cell["status"]] = statuses.get(cell["status"], 0) + 1
        return {
            "pair_count": len(pairs),
            "matched_pairs": sum(1 for pair in pairs if pair["row_state"] == "paired"),
            "missing_base_pairs": sum(1 for pair in pairs if pair["row_state"] == "missing_base"),
            "missing_control_pairs": sum(1 for pair in pairs if pair["row_state"] == "missing_control"),
            "adjudicated_pairs": sum(1 for pair in pairs if pair.get("adjudicated")),
            "cell_count": sum(len(pair["cells"]) for pair in pairs),
            "diff_cells": statuses.get("diff", 0),
            "within_cells": statuses.get("within", 0),
            "missing_cells": statuses.get("missing", 0),
            "null_cells": statuses.get("null", 0),
            "quarantine_groups": len(groups),
            "unresolved_quarantine_groups": sum(1 for group in groups if not group.get("resolution")),
            "quarantined_rows": sum(len(group["base_records"]) + len(group["control_records"]) for group in groups),
            "adjudicated_quarantined_rows": sum(
                len(group["base_records"]) + len(group["control_records"])
                for group in groups if group.get("resolution")
            ),
            "base_records": int((entry.get("source_counts") or {}).get("base_records", 0)),
            "control_records": int((entry.get("source_counts") or {}).get("control_records", 0)),
        }


def _resolve_side_dataset(plan: dict[str, Any], *, base: bool) -> dict[str, Any] | None:
    code_field = "基线数据集编号" if base else "对照数据集编号"
    name_field = "基准数据集" if base else "对照数据集"
    return _dataset_by_code(plan.get(code_field)) or _dataset_by_name(plan.get(name_field))


def _dataset_brief(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": dataset.get("id"),
        "code": dataset.get("数据集编号"),
        "name": dataset.get("数据集名称"),
        "source_table": dataset.get("来源表名"),
        "status": dataset.get("status"),
        "fields": dataset_fields(dataset),
    }


def _seal_dataset(dataset: dict[str, Any], role: str) -> dict[str, Any]:
    brief = _dataset_brief(dataset)
    return {
        "role": role,
        "code": brief["code"],
        "name": brief["name"],
        "source_table": brief["source_table"],
        "status_at_seal": brief["status"],
        "fields": copy.deepcopy(brief["fields"]),
        "record_count": len(records_for_dataset(str(brief["code"]))),
        "digest": _digest({key: brief[key] for key in ("code", "name", "source_table", "fields")}),
    }


def _side_identity(sealed: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": sealed.get("role"),
        "code": sealed.get("code"),
        "name": sealed.get("name"),
        "source_table": sealed.get("source_table"),
        "status_at_seal": sealed.get("status_at_seal"),
        "digest": sealed.get("digest"),
        "record_count": sealed.get("record_count"),
    }


def _snapshot_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": snapshot.get("plan_id"),
        "plan_no": snapshot.get("plan_no"),
        "round_no": snapshot.get("round_no"),
        "sealed_at": snapshot.get("sealed_at"),
        "diff_direction": snapshot.get("diff_direction", "对照 - 基准"),
        "digest": snapshot.get("digest"),
        "swap_of": snapshot.get("swap_of"),
        "base": _side_identity(snapshot["base"]),
        "control": _side_identity(snapshot["control"]),
        "mapping": copy.deepcopy(snapshot["mapping"]),
        "thresholds": copy.deepcopy(snapshot.get("thresholds") or {}),
    }


def _thresholds(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        str(field.get("label") or field.get("base")): {
            "threshold": field.get("threshold", 0),
            "mode": field.get("threshold_mode", "absolute"),
            "base": field.get("base"),
            "control": field.get("control"),
        }
        for field in mapping.get("value_fields") or []
    }


def _swap_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "business_keys": [
            {"base": item.get("control"), "control": item.get("base"), "label": item.get("label")}
            for item in mapping.get("business_keys") or []
        ],
        "value_fields": [
            {
                "base": item.get("control"),
                "control": item.get("base"),
                "label": item.get("label"),
                "threshold": item.get("threshold", 0),
                "threshold_mode": item.get("threshold_mode", "absolute"),
            }
            for item in mapping.get("value_fields") or []
        ],
    }


def _mapping_problems(mapping: dict[str, Any], base: dict[str, Any], control: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(mapping.get("business_keys"), list) or not mapping["business_keys"]:
        problems.append("至少需要一个业务键字段")
    if not isinstance(mapping.get("value_fields"), list) or not mapping["value_fields"]:
        problems.append("至少需要一个数值对比字段")
    base_fields = _field_map(base)
    control_fields = _field_map(control)
    for item in mapping.get("business_keys") or []:
        if item.get("base") not in base_fields:
            problems.append(f"业务键基准字段 {item.get('base')} 不在基准数据集字段中")
        if item.get("control") not in control_fields:
            problems.append(f"业务键对照字段 {item.get('control')} 不在对照数据集字段中")
    for item in mapping.get("value_fields") or []:
        if item.get("base") not in base_fields:
            problems.append(f"对比字段基准字段 {item.get('base')} 不在基准数据集字段中")
        if item.get("control") not in control_fields:
            problems.append(f"对比字段对照字段 {item.get('control')} 不在对照数据集字段中")
        try:
            threshold = float(item.get("threshold", 0))
        except (TypeError, ValueError):
            problems.append(f"字段 {item.get('label')} 的阈值不是数值")
            continue
        if threshold < 0:
            problems.append(f"字段 {item.get('label')} 的阈值不能为负数")
    return problems


def _validate_mapping(mapping: dict[str, Any], base: dict[str, Any], control: dict[str, Any]) -> list[str]:
    return _mapping_problems(mapping, base, control)


def _derive_mapping(plan: dict[str, Any], base: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    """没有登记映射时按字段标签对齐，优先把“编号/号”类字段当业务键。"""
    base_fields = dataset_fields(base)
    control_fields = dataset_fields(control)
    by_label_control = {field["label"]: field for field in control_fields}
    common = [(field, by_label_control[field["label"]]) for field in base_fields if field["label"] in by_label_control]
    key_pair = next((pair for pair in common if "号" in pair[0]["label"] or "编号" in pair[0]["label"]), None)
    if key_pair is None and common:
        key_pair = common[0]
    business_keys = [{
        "base": key_pair[0]["name"],
        "control": key_pair[1]["name"],
        "label": key_pair[0]["label"],
    }] if key_pair else []
    values: list[dict[str, Any]] = []
    for base_field, control_field in common:
        if key_pair and base_field["name"] == key_pair[0]["name"]:
            continue
        if control_field["type"] not in ("number", "integer") and base_field["type"] not in ("number", "integer"):
            continue
        values.append({
            "base": base_field["name"],
            "control": control_field["name"],
            "label": base_field["label"],
            "threshold": 0,
            "threshold_mode": "absolute",
        })
    return {"business_keys": business_keys, "value_fields": values}


def _deprecation_blockers(snapshot: dict[str, Any]) -> list[str]:
    """封存后任一侧被废弃即阻断——按变更日志判断，避免“废弃后又被恢复”绕过检查。"""
    blockers: list[str] = []
    sealed_at = str(snapshot.get("sealed_at") or "")
    for role, side in ((SIDE_BASE, snapshot["base"]), (SIDE_CONTROL, snapshot["control"])):
        current = _dataset_by_code(side.get("code"))
        if current is None:
            blockers.append(f"{role}数据集「{side.get('name')}」已不存在，封存定义失效")
            continue
        if current.get("status") == "已废弃":
            blockers.append(
                f"{role}数据集「{side.get('name')}」已被废弃（封存时为「{side.get('status_at_seal')}」），"
                "计算结果失去依据，阻止结论签认"
            )
            continue
        # 当前状态可能已经恢复；只要封存后出现过“废弃”变更，本轮仍不可签认。
        for event in store.dataset_status_events(str(side.get("code"))):
            if event.get("to") == "已废弃" and str(event.get("at") or "") >= sealed_at:
                blockers.append(
                    f"{role}数据集「{side.get('name')}」在封存后曾被废弃（{event.get('at')}），"
                    "即使后来恢复，本轮结论也不能签认，请重算"
                )
                break
    return blockers


def _definition_warnings(snapshot: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for role, side in ((SIDE_BASE, snapshot["base"]), (SIDE_CONTROL, snapshot["control"])):
        current = _dataset_by_code(side.get("code"))
        if current is None:
            continue
        current_fields = dataset_fields(current)
        if current_fields != side.get("fields"):
            warnings.append(f"{role}数据集「{side.get('name')}」当前字段定义与封存时不一致，请复核字段身份")
        if current.get("status") != side.get("status_at_seal"):
            warnings.append(
                f"{role}数据集「{side.get('name')}」状态已由「{side.get('status_at_seal')}」变为"
                f"「{current.get('status')}」"
            )
    return warnings


def _pair_has(pair: dict[str, Any], status: str) -> bool:
    return any(cell["status"] == status for cell in pair.get("cells") or [])


def _assign_pair_id(existing: list[dict[str, Any]], pair: dict[str, Any]) -> None:
    """pair_id 要在格子生成前确定，所以先在草稿上算好编号再回填到格子里。"""
    pair_id = f"P-{len(existing) + 1:03d}"
    pair["pair_id"] = pair_id
    for cell in pair["cells"]:
        cell["cell_id"] = f"{pair_id}:{cell['field_index']}"


def _locate_cell(entry: dict[str, Any], cell_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for pair in entry.get("pairs") or []:
        for cell in pair.get("cells") or []:
            if cell.get("cell_id") == cell_id:
                return pair, cell
    return None, None


def _record_brief(record: dict[str, Any]) -> dict[str, Any]:
    return {"record_id": record.get("record_id"), "values": copy.deepcopy(record.get("values") or {})}


def _side_evidence(sealed: dict[str, Any], record_id: str | None, record: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "role": sealed.get("role"),
        "dataset_code": sealed.get("code"),
        "dataset_name": sealed.get("name"),
        "source_table": sealed.get("source_table"),
        "record_id": record_id,
        "values": copy.deepcopy((record or {}).get("values") or {}),
        "present": record is not None,
        "sealed_digest": sealed.get("digest"),
    }


def _query_for_dataset(sealed: dict[str, Any]) -> dict[str, Any] | None:
    target = str(sealed.get("name") or "")
    for row in store.rows("query"):
        if str(row.get("目标数据集") or "") == target:
            return {
                "id": row.get("id"),
                "statement_no": row.get("语句编号"),
                "expression": row.get("查询表达式"),
                "target_dataset": row.get("目标数据集"),
                "status": row.get("status"),
            }
    return None


compare_matrix_service = CompareMatrixService()
