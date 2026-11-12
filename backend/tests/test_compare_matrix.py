"""对比分析差异矩阵的关键不变量测试（标准库 unittest，无额外依赖）。

运行：cd backend && .venv/bin/python -m unittest tests.test_compare_matrix -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sample_data import DATASET_RECORDS
from app.services.compare_matrix import compare_matrix_service
from app.store import store


class CompareMatrixBase(unittest.TestCase):
    def setUp(self) -> None:
        # 每个用例重新装载示例数据，避免用例之间互相污染。
        from app import seed

        store._tables = {name: [dict(row) for row in rows] for name, rows in seed.SEED_ROWS.items()}
        store._dataset_status_log = []
        compare_matrix_service._rounds = {}
        compare_matrix_service._next_round_id = 1
        compare_matrix_service._round_seq = {}

    def start_complete(self, plan_id: int = 1) -> dict:
        brief, message = compare_matrix_service.create_round(plan_id)
        self.assertIsNotNone(brief, message)
        result, message = compare_matrix_service.complete_round(brief["id"])
        self.assertIsNotNone(result, message)
        return result

    def matrix(self, round_id: int) -> dict:
        payload, message = compare_matrix_service.matrix_page(round_id, size=200)
        self.assertIsNotNone(payload, message)
        return payload

    def pair_by_key(self, matrix: dict, key: str) -> dict:
        return next(pair for pair in matrix["items"] if pair["key"] == key)


class PairingTests(CompareMatrixBase):
    def test_business_key_pairs_are_unique_and_counts_are_stable(self):
        round_brief = self.start_complete()
        matrix = self.matrix(round_brief["id"])
        summary = matrix["summary"]
        self.assertEqual(summary["base_records"], len(DATASET_RECORDS["DATA-0001"]))
        self.assertEqual(summary["control_records"], len(DATASET_RECORDS["DATA-0002"]))
        # 两侧每一行都必须有归属：成对、缺行或隔离，不能静默丢行。
        # 已裁决的隔离组会额外生成一条人工配对，那一组的行在隔离区与配对中各计一次，属于预期。
        accounted = (
            2 * summary["matched_pairs"]
            + summary["missing_base_pairs"]
            + summary["missing_control_pairs"]
            + summary["quarantined_rows"]
        )
        self.assertEqual(accounted, summary["base_records"] + summary["control_records"])
        # 不能按输入顺序配对：重复键组的行一条都不能出现在普通配对里
        for key in ("O-1010", "O-1020", "O-1030"):
            self.assertFalse(any(pair["key"] == key for pair in matrix["items"]))

    def test_duplicate_keys_go_to_quarantine_with_all_rows(self):
        round_brief = self.start_complete()
        detail, message = compare_matrix_service.get_round(round_brief["id"])
        self.assertIsNotNone(detail, message)
        groups = detail["quarantine_groups"]
        self.assertEqual(len(groups), 4)
        group = next(item for item in groups if item["key"] == "O-1030")
        self.assertEqual(len(group["base_records"]), 2)
        self.assertEqual(len(group["control_records"]), 2)
        self.assertIsNone(group["resolution"])
        empty_key = next(item for item in groups if item["key"] == "（空业务键）")
        self.assertIn("业务键为空", empty_key["reason"])

    def test_missing_rows_marked_per_side(self):
        matrix = self.matrix(self.start_complete()["id"])
        self.assertEqual(self.pair_by_key(matrix, "O-1008")["row_state"], "missing_control")
        self.assertEqual(self.pair_by_key(matrix, "O-2001")["row_state"], "missing_base")
        self.assertTrue(all(cell["status"] == "missing" for cell in self.pair_by_key(matrix, "O-1008")["cells"]))


class CellValueTests(CompareMatrixBase):
    def test_blank_string_and_numeric_zero_are_not_equal(self):
        matrix = self.matrix(self.start_complete()["id"])
        cell = self.pair_by_key(matrix, "O-1005")["cells"][0]
        self.assertEqual(cell["status"], "null")
        self.assertIsNone(cell["diff"])
        self.assertEqual(cell["base_kind"], "blank")
        self.assertEqual(cell["control_kind"], "number")
        self.assertIn("不是同一取值", cell["null_note"])

    def test_both_null_is_null_not_zero(self):
        cell = self.pair_by_key(self.matrix(self.start_complete()["id"]), "O-1007")["cells"][0]
        self.assertEqual(cell["status"], "null")
        self.assertEqual(cell["state_detail"], "both_blank")

    def test_threshold_boundary_inclusive(self):
        matrix = self.matrix(self.start_complete()["id"])
        # O-1002：80.5 -> 60.5，差值 -20，阈值 20，属于阈值内
        self.assertEqual(self.pair_by_key(matrix, "O-1002")["cells"][0]["status"], "within")
        # O-1001：120 -> 135，差值 +15，阈值 20，属于阈值内
        self.assertEqual(self.pair_by_key(matrix, "O-1001")["cells"][0]["diff"], 15.0)
        # O-1006：45 -> 80，差值 +35，超过阈值
        self.assertEqual(self.pair_by_key(matrix, "O-1006")["cells"][0]["status"], "diff")

    def test_zero_to_zero_is_within(self):
        cell = self.pair_by_key(self.matrix(self.start_complete()["id"]), "O-1003")["cells"][0]
        self.assertEqual(cell["status"], "within")
        self.assertEqual(cell["diff"], 0.0)


class RoundLifecycleTests(CompareMatrixBase):
    def test_deprecation_during_computation_blocks_signoff(self):
        brief, message = compare_matrix_service.create_round(1)
        self.assertIsNotNone(brief, message)
        base = next(row for row in store.rows("datastore") if row["数据集编号"] == "DATA-0001")
        store.record_dataset_status(base, base["status"], "废弃下线")
        base["status"] = "已废弃"
        result, message = compare_matrix_service.complete_round(brief["id"])
        self.assertIsNotNone(result, message)
        self.assertEqual(result["status"], "已阻断")
        self.assertTrue(result["block_reasons"])
        signed, signoff_message = compare_matrix_service.signoff_round(brief["id"], "复核")
        self.assertIsNone(signed)
        self.assertIn("废弃", signoff_message)
        # 矩阵本身仍然可见
        matrix = self.matrix(brief["id"])
        self.assertGreater(matrix["total"], 0)

    def test_deprecation_then_restore_still_blocks_the_round(self):
        brief, message = compare_matrix_service.create_round(1)
        self.assertIsNotNone(brief, message)
        base = next(row for row in store.rows("datastore") if row["数据集编号"] == "DATA-0001")
        store.record_dataset_status(base, base["status"], "废弃下线")
        base["status"] = "已废弃"
        store.record_dataset_status(base, "已废弃", "生效发布")
        base["status"] = "已生效"
        compare_matrix_service.complete_round(brief["id"])
        detail, message = compare_matrix_service.get_round(brief["id"])
        self.assertIsNotNone(detail, message)
        self.assertTrue(any("封存后曾被废弃" in reason for reason in detail["blockers"]))
        signed, signoff_message = compare_matrix_service.signoff_round(brief["id"], "复核")
        self.assertIsNone(signed)
        self.assertIn("封存后曾被废弃", signoff_message)

    def test_recompute_keeps_old_round_snapshot_and_thresholds(self):
        first = self.start_complete()
        plan = next(row for row in store.rows("compare") if int(row["id"]) == 1)
        plan["字段映射"]["value_fields"][0]["threshold"] = 5
        second, message = compare_matrix_service.create_round(1, parent_round_id=first["id"])
        self.assertIsNotNone(second, message)
        self.assertEqual(second["parent_round_id"], first["id"])
        compare_matrix_service.complete_round(second["id"])
        old, _ = compare_matrix_service.get_round(first["id"])
        new, _ = compare_matrix_service.get_round(second["id"])
        self.assertEqual(old["snapshot"]["thresholds"]["成交金额"]["threshold"], 20)
        self.assertEqual(new["snapshot"]["thresholds"]["成交金额"]["threshold"], 5)
        self.assertEqual(old["snapshot"]["digest"] == new["snapshot"]["digest"], False)

    def test_swap_reverses_diff_direction_and_still_blocks_unresolved(self):
        first = self.start_complete()
        swapped, message = compare_matrix_service.swap_round(first["id"])
        self.assertIsNotNone(swapped, message)
        compare_matrix_service.complete_round(swapped["id"])
        original = self.pair_by_key(self.matrix(first["id"]), "O-1006")["cells"][0]
        mirrored = self.pair_by_key(self.matrix(swapped["id"]), "O-1006")["cells"][0]
        self.assertEqual(mirrored["diff"], -original["diff"])
        self.assertEqual(mirrored["base_raw"], original["control_raw"])

    def test_signoff_requires_quarantine_resolution(self):
        brief = self.start_complete()
        signed, message = compare_matrix_service.signoff_round(brief["id"], "复核")
        self.assertIsNone(signed)
        self.assertIn("歧义键组", message)
        detail, _ = compare_matrix_service.get_round(brief["id"])
        for group in detail["quarantine_groups"]:
            result, message = compare_matrix_service.resolve_quarantine(
                brief["id"], group["group_id"], decision="整组不比较", base_record_id=None,
                control_record_id=None, note="键定义不足",
            )
            self.assertIsNotNone(result, message)
        signed, message = compare_matrix_service.signoff_round(brief["id"], "复核完成")
        self.assertIsNotNone(signed, message)
        self.assertEqual(signed["status"], "已签认")


class AuditTests(CompareMatrixBase):
    def test_cell_trace_returns_mapping_and_basis(self):
        round_brief = self.start_complete()
        cell_id = self.matrix(round_brief["id"])["items"][0]["cells"][0]["cell_id"]
        detail, message = compare_matrix_service.cell_detail(round_brief["id"], cell_id)
        self.assertIsNotNone(detail, message)
        trace = detail["trace"]
        self.assertEqual(trace["match_basis"], "业务键唯一匹配")
        self.assertEqual(trace["field_mapping"]["base"], "amount")
        self.assertEqual(trace["field_mapping"]["control"], "pay_amount")
        self.assertEqual(trace["snapshot_digest"], round_brief["snapshot"]["digest"])

    def test_evidence_links_cross_module_query(self):
        round_brief = self.start_complete()
        cell_id = self.matrix(round_brief["id"])["items"][0]["cells"][0]["cell_id"]
        evidence, message = compare_matrix_service.cell_evidence(round_brief["id"], cell_id)
        self.assertIsNotNone(evidence, message)
        self.assertEqual(evidence["queries"]["base"]["statement_no"], "QUER-0001")
        self.assertEqual(evidence["queries"]["control"]["statement_no"], "QUER-0002")

    def test_quarantine_resolution_requires_explicit_both_sides(self):
        brief = self.start_complete()
        detail, _ = compare_matrix_service.get_round(brief["id"])
        group = next(item for item in detail["quarantine_groups"] if item["key"] == "O-1020")
        result, message = compare_matrix_service.resolve_quarantine(
            brief["id"], group["group_id"], decision="确认配对",
            base_record_id="ORD-B1020", control_record_id=None,
        )
        self.assertIsNone(result)
        self.assertIn("对照侧", message)
        result, message = compare_matrix_service.resolve_quarantine(
            brief["id"], group["group_id"], decision="确认配对",
            base_record_id="ORD-B1020", control_record_id="ORD-C1020A", note="按更新时间",
        )
        self.assertIsNotNone(result, message)
        matrix = self.matrix(brief["id"])
        adjudicated = next(pair for pair in matrix["items"] if pair.get("adjudicated"))
        self.assertEqual(adjudicated["control_record_id"], "ORD-C1020A")
        self.assertIn("ORD-C1020B", adjudicated["ignored_control_record_ids"])

    def test_empty_key_group_with_missing_side_requires_explicit_present_record(self):
        brief = self.start_complete()
        detail, _ = compare_matrix_service.get_round(brief["id"])
        group = next(item for item in detail["quarantine_groups"] if item["key"] == "（空业务键）")
        self.assertEqual(group["control_records"], [])
        # 不点选存在的一侧记录，不能确认
        result, message = compare_matrix_service.resolve_quarantine(
            brief["id"], group["group_id"], decision="确认配对",
            base_record_id=None, control_record_id=None,
        )
        self.assertIsNone(result)
        self.assertIn("基准侧", message)
        result, message = compare_matrix_service.resolve_quarantine(
            brief["id"], group["group_id"], decision="确认配对",
            base_record_id=group["base_records"][0]["record_id"], control_record_id=None,
            note="对照侧整侧缺行",
        )
        self.assertIsNotNone(result, message)
        matrix = self.matrix(brief["id"])
        pair = next(item for item in matrix["items"] if item.get("adjudicated") and item["key"] == "（空业务键）")
        self.assertEqual(pair["row_state"], "missing_control")


class MappingValidationTests(unittest.TestCase):
    def test_unknown_field_rejected(self):
        result, message = compare_matrix_service.replace_mapping(
            1,
            {"business_keys": [{"base": "nope", "control": "order_no", "label": "订单号"}],
             "value_fields": [{"base": "amount", "control": "pay_amount", "label": "金额", "threshold": 0, "threshold_mode": "absolute"}]},
            base_dataset_code="DATA-0001", control_dataset_code="DATA-0002",
        )
        self.assertIsNone(result)
        self.assertIn("nope", message)

    def test_same_dataset_rejected_in_preview(self):
        result, message = compare_matrix_service.preview_mapping("DATA-0001", "DATA-0001")
        self.assertIsNone(result)
        self.assertIn("同一个数据集", message)

    def test_negative_threshold_rejected(self):
        result, message = compare_matrix_service.replace_mapping(
            1,
            {"business_keys": [{"base": "order_id", "control": "order_no", "label": "订单号"}],
             "value_fields": [{"base": "amount", "control": "pay_amount", "label": "金额", "threshold": -1, "threshold_mode": "absolute"}]},
            base_dataset_code="DATA-0001", control_dataset_code="DATA-0002",
        )
        self.assertIsNone(result)
        self.assertIn("负数", message)


if __name__ == "__main__":
    unittest.main()
