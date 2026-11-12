"""对比样本数据：按数据集编号组织，供成对差异矩阵取数。

数据里刻意保留了真实对比时会遇到的几种边界：
- 同一业务键在某一侧出现多行（歧义键组，必须进隔离区，不允许按输入顺序配对）；
- 只有一侧存在的业务键（缺行）；
- 数值为空值（None）、空字符串（""）、数字 0 三种不同取值；
- 数值差超出阈值与未超阈值。
"""
from __future__ import annotations

import copy
from typing import Any


def _row(record_id: str, **values: Any) -> dict[str, Any]:
    return {"record_id": record_id, "values": values}


def _order_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """订单明细的基准/对照样本：显式边界记录 + 一批大结果集记录。"""
    base: list[dict[str, Any]] = [
        _row("ORD-B1001", order_id="O-1001", region="华东", channel="线上",
             amount=120.0, qty=3, order_status="已支付", updated_at="2026-10-01 09:00:00"),
        _row("ORD-B1002", order_id="O-1002", region="华南", channel="门店",
             amount=80.5, qty=2, order_status="已支付", updated_at="2026-10-01 09:05:00"),
        _row("ORD-B1003", order_id="O-1003", region="华北", channel="线上",
             amount=0, qty=0, order_status="已支付", updated_at="2026-10-01 09:10:00"),
        _row("ORD-B1004", order_id="O-1004", region="西南", channel="门店",
             amount=None, qty=1, order_status="已支付", updated_at="2026-10-01 09:15:00"),
        _row("ORD-B1005", order_id="O-1005", region="华东", channel="门店",
             amount="", qty=2, order_status="已支付", updated_at="2026-10-01 09:20:00"),
        _row("ORD-B1006", order_id="O-1006", region="西北", channel="线上",
             amount=45.0, qty=4, order_status="已支付", updated_at="2026-10-01 09:25:00"),
        _row("ORD-B1007", order_id="O-1007", region="华东", channel="线上",
             amount=None, qty=None, order_status="已支付", updated_at="2026-10-01 09:30:00"),
        _row("ORD-B1008", order_id="O-1008", region="华南", channel="线上",
             amount=300.0, qty=5, order_status="已支付", updated_at="2026-10-01 09:35:00"),
        _row("ORD-B1009", order_id="O-1009", region="华北", channel="门店",
             amount=200.0, qty=3, order_status="已支付", updated_at="2026-10-01 09:40:00"),
        # O-1010 在基准侧重复，对照侧唯一：整组进隔离区
        _row("ORD-B1010A", order_id="O-1010", region="华东", channel="线上",
             amount=88.0, qty=2, order_status="已支付", updated_at="2026-10-01 09:45:00"),
        _row("ORD-B1010B", order_id="O-1010", region="华南", channel="门店",
             amount=90.0, qty=2, order_status="已支付", updated_at="2026-10-01 09:46:00"),
        _row("ORD-B1011", order_id="O-1011", region="西南", channel="线上",
             amount=60.75, qty=1, order_status="已支付", updated_at="2026-10-01 09:50:00"),
        _row("ORD-B1012", order_id="O-1012", region="东北", channel="门店",
             amount=15.25, qty=2, order_status="已支付", updated_at="2026-10-01 09:55:00"),
        _row("ORD-B1013", order_id="O-1013", region="华东", channel="线上",
             amount=0, qty=0, order_status="已支付", updated_at="2026-10-01 10:00:00"),
        _row("ORD-B1014", order_id="O-1014", region="华北", channel="门店",
             amount=99.99, qty=1, order_status="已支付", updated_at="2026-10-01 10:05:00"),
        _row("ORD-B1015", order_id="O-1015", region="华南", channel="线上",
             amount=42.0, qty=2, order_status="已支付", updated_at="2026-10-01 10:10:00"),
        _row("ORD-B1016", order_id="O-1016", region="西北", channel="门店",
             amount=55.0, qty=1, order_status="已支付", updated_at="2026-10-01 10:15:00"),
        _row("ORD-B1017", order_id="O-1017", region="东北", channel="线上",
             amount=5.0, qty=1, order_status="已支付", updated_at="2026-10-01 10:20:00"),
        _row("ORD-B1018", order_id="O-1018", region="华东", channel="门店",
             amount=110.0, qty=2, order_status="已支付", updated_at="2026-10-01 10:25:00"),
        _row("ORD-B1019", order_id="O-1019", region="华南", channel="线上",
             amount=None, qty=1, order_status="已支付", updated_at="2026-10-01 10:30:00"),
        _row("ORD-B1020", order_id="O-1020", region="华北", channel="线上",
             amount=70.0, qty=2, order_status="已支付", updated_at="2026-10-01 10:35:00"),
        # O-1030 两侧都重复：无论输入顺序如何都不能自动配对
        _row("ORD-B1030A", order_id="O-1030", region="西南", channel="门店",
             amount=33.0, qty=1, order_status="已支付", updated_at="2026-10-01 10:40:00"),
        _row("ORD-B1030B", order_id="O-1030", region="西南", channel="线上",
             amount=34.0, qty=1, order_status="已支付", updated_at="2026-10-01 10:41:00"),
        # 业务键为空：不能与任何一侧空键记录自动配对
        _row("ORD-B9001", order_id="", region="华东", channel="线上",
             amount=10.0, qty=1, order_status="已支付", updated_at="2026-10-01 11:30:00"),
    ]

    control: list[dict[str, Any]] = [
        _row("ORD-C1001", order_no="O-1001", area="华东", source="线上",
             pay_amount=135.0, item_count=3, status_desc="已支付", update_time="2026-10-01 09:00:00"),
        _row("ORD-C1002", order_no="O-1002", area="华南", source="门店",
             pay_amount=60.5, item_count=2, status_desc="已支付", update_time="2026-10-01 09:05:00"),
        _row("ORD-C1003", order_no="O-1003", area="华北", source="线上",
             pay_amount=0, item_count=0, status_desc="已支付", update_time="2026-10-01 09:10:00"),
        _row("ORD-C1004", order_no="O-1004", area="西南", source="门店",
             pay_amount=30.0, item_count=1, status_desc="已支付", update_time="2026-10-01 09:15:00"),
        # 基准是空字符串，对照是数字 0：不得判成“相等”
        _row("ORD-C1005", order_no="O-1005", area="华东", source="门店",
             pay_amount=0, item_count=2, status_desc="已支付", update_time="2026-10-01 09:20:00"),
        _row("ORD-C1006", order_no="O-1006", area="西北", source="线上",
             pay_amount=80.0, item_count=4, status_desc="已支付", update_time="2026-10-01 09:25:00"),
        _row("ORD-C1007", order_no="O-1007", area="华东", source="线上",
             pay_amount=None, item_count=None, status_desc="已支付", update_time="2026-10-01 09:30:00"),
        # O-1008 对照缺行
        _row("ORD-C1009", order_no="O-1009", area="华北", source="门店",
             pay_amount=120.0, item_count=3, status_desc="已支付", update_time="2026-10-01 09:40:00"),
        _row("ORD-C1010", order_no="O-1010", area="华东", source="线上",
             pay_amount=89.0, item_count=2, status_desc="已支付", update_time="2026-10-01 09:45:00"),
        _row("ORD-C1011", order_no="O-1011", area="西南", source="线上",
             pay_amount=88.75, item_count=1, status_desc="已支付", update_time="2026-10-01 09:50:00"),
        _row("ORD-C1012", order_no="O-1012", area="东北", source="门店",
             pay_amount=15.25, item_count=2, status_desc="已支付", update_time="2026-10-01 09:55:00"),
        _row("ORD-C1013", order_no="O-1013", area="华东", source="线上",
             pay_amount=0, item_count=0, status_desc="已支付", update_time="2026-10-01 10:00:00"),
        _row("ORD-C1014", order_no="O-1014", area="华北", source="门店",
             pay_amount=112.0, item_count=1, status_desc="已支付", update_time="2026-10-01 10:05:00"),
        _row("ORD-C1015", order_no="O-1015", area="华南", source="线上",
             pay_amount=20.0, item_count=2, status_desc="已支付", update_time="2026-10-01 10:10:00"),
        _row("ORD-C1016", order_no="O-1016", area="西北", source="门店",
             pay_amount=55.0001, item_count=1, status_desc="已支付", update_time="2026-10-01 10:15:00"),
        _row("ORD-C1017", order_no="O-1017", area="东北", source="线上",
             pay_amount=0, item_count=1, status_desc="已支付", update_time="2026-10-01 10:20:00"),
        # O-1018 对照缺行
        _row("ORD-C1019", order_no="O-1019", area="华南", source="线上",
             pay_amount=110.0, item_count=1, status_desc="已支付", update_time="2026-10-01 10:30:00"),
        # O-1020 对照侧重复，基准侧唯一：整组进隔离区
        _row("ORD-C1020A", order_no="O-1020", area="华北", source="线上",
             pay_amount=71.0, item_count=2, status_desc="已支付", update_time="2026-10-01 10:35:00"),
        _row("ORD-C1020B", order_no="O-1020", area="华南", source="门店",
             pay_amount=72.0, item_count=2, status_desc="已支付", update_time="2026-10-01 10:36:00"),
        _row("ORD-C1030A", order_no="O-1030", area="西南", source="门店",
             pay_amount=35.0, item_count=1, status_desc="已支付", update_time="2026-10-01 10:40:00"),
        _row("ORD-C1030B", order_no="O-1030", area="西南", source="线上",
             pay_amount=36.0, item_count=1, status_desc="已支付", update_time="2026-10-01 10:41:00"),
        # 只有对照侧存在的两行 -> 基准缺行
        _row("ORD-C2001", order_no="O-2001", area="华北", source="门店",
             pay_amount=150.0, item_count=2, status_desc="已支付", update_time="2026-10-01 11:00:00"),
        _row("ORD-C2002", order_no="O-2002", area="东北", source="线上",
             pay_amount=25.0, item_count=1, status_desc="已支付", update_time="2026-10-01 11:05:00"),
    ]

    regions = ["华东", "华南", "华北", "西南", "西北", "东北"]
    channels = ["线上", "门店"]
    for index in range(50):
        key = f"O-{3000 + index}"
        base_amount = round(20.0 + index * 7.35, 2)
        control_amount = round(base_amount + ((index % 7) - 2) * 13.4, 2)
        base.append(_row(
            f"ORD-B3{index:03d}", order_id=key, region=regions[index % len(regions)],
            channel=channels[index % len(channels)], amount=base_amount,
            qty=(index % 5) + 1, order_status="已支付",
            updated_at=f"2026-10-02 {8 + index // 6:02d}:{(index * 7) % 60:02d}:00",
        ))
        control.append(_row(
            f"ORD-C3{index:03d}", order_no=key, area=regions[index % len(regions)],
            source=channels[index % len(channels)], pay_amount=control_amount,
            item_count=(index % 5) + 1, status_desc="已支付",
            update_time=f"2026-10-02 {8 + index // 6:02d}:{(index * 7) % 60:02d}:00",
        ))
    return base, control


def _member_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base: list[dict[str, Any]] = [
        _row("MEM-B001", member_id="M-001", city="上海", channel="APP",
             active_days=18, order_cnt=4, last_login="2026-10-01 08:00:00"),
        _row("MEM-B002", member_id="M-002", city="北京", channel="小程序",
             active_days=0, order_cnt=0, last_login="2026-10-01 08:10:00"),
        _row("MEM-B003", member_id="M-003", city="深圳", channel="APP",
             active_days=None, order_cnt=1, last_login="2026-10-01 08:20:00"),
        _row("MEM-B004", member_id="M-004", city="广州", channel="门店",
             active_days="", order_cnt=2, last_login="2026-10-01 08:30:00"),
        _row("MEM-B005", member_id="M-005", city="杭州", channel="APP",
             active_days=12, order_cnt=3, last_login="2026-10-01 08:40:00"),
        _row("MEM-B006", member_id="M-006", city="成都", channel="小程序",
             active_days=7, order_cnt=2, last_login="2026-10-01 08:50:00"),
        # 基准重复
        _row("MEM-B007A", member_id="M-007", city="上海", channel="APP",
             active_days=22, order_cnt=5, last_login="2026-10-01 09:00:00"),
        _row("MEM-B007B", member_id="M-007", city="北京", channel="门店",
             active_days=23, order_cnt=5, last_login="2026-10-01 09:01:00"),
        _row("MEM-B008", member_id="M-008", city="深圳", channel="APP",
             active_days=30, order_cnt=6, last_login="2026-10-01 09:10:00"),
    ]
    control: list[dict[str, Any]] = [
        _row("MEM-C001", member_no="M-001", region_city="上海", src_ch="APP",
             active_days=20, orders=4, last_login_at="2026-10-01 08:00:00"),
        _row("MEM-C002", member_no="M-002", region_city="北京", src_ch="小程序",
             active_days=0, orders=0, last_login_at="2026-10-01 08:10:00"),
        _row("MEM-C003", member_no="M-003", region_city="深圳", src_ch="APP",
             active_days=9, orders=1, last_login_at="2026-10-01 08:20:00"),
        _row("MEM-C004", member_no="M-004", region_city="广州", src_ch="门店",
             active_days=0, orders=2, last_login_at="2026-10-01 08:30:00"),
        _row("MEM-C005", member_no="M-005", region_city="杭州", src_ch="APP",
             active_days=None, orders=3, last_login_at="2026-10-01 08:40:00"),
        # M-006 对照缺行
        _row("MEM-C007", member_no="M-007", region_city="上海", src_ch="APP",
             active_days=24, orders=5, last_login_at="2026-10-01 09:00:00"),
        _row("MEM-C008", member_no="M-008", region_city="深圳", src_ch="APP",
             active_days=28, orders=6, last_login_at="2026-10-01 09:10:00"),
        _row("MEM-C009", member_no="M-009", region_city="成都", src_ch="小程序",
             active_days=6, orders=2, last_login_at="2026-10-01 09:20:00"),
    ]
    cities = ["上海", "北京", "深圳", "广州", "杭州", "成都"]
    channels = ["APP", "小程序", "门店"]
    for index in range(30):
        key = f"M-{100 + index}"
        base_days = (index % 11) + 2
        control_days = base_days + ((index % 5) - 2)
        base.append(_row(
            f"MEM-B1{index:03d}", member_id=key, city=cities[index % len(cities)],
            channel=channels[index % len(channels)], active_days=base_days,
            order_cnt=(index % 6) + 1, last_login=f"2026-10-02 07:{index % 60:02d}:00",
        ))
        control.append(_row(
            f"MEM-C1{index:03d}", member_no=key, region_city=cities[index % len(cities)],
            src_ch=channels[index % len(channels)], active_days=control_days,
            orders=(index % 6) + 1, last_login_at=f"2026-10-02 07:{index % 60:02d}:00",
        ))
    return base, control


_ORDER_BASE, _ORDER_CONTROL = _order_records()
_MEMBER_BASE, _MEMBER_CONTROL = _member_records()

DATASET_RECORDS: dict[str, list[dict[str, Any]]] = {
    "DATA-0001": _ORDER_BASE,
    "DATA-0002": _ORDER_CONTROL,
    "DATA-0003": _MEMBER_BASE,
    "DATA-0004": _MEMBER_CONTROL,
}


def records_for_dataset(code: str) -> list[dict[str, Any]]:
    """返回数据集样本的深拷贝，避免调用方改动原始示例数据。"""
    return copy.deepcopy(DATASET_RECORDS.get(code, []))
