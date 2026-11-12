"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class CompareMappingPayload(BaseModel):
    """字段映射：业务键与数值字段的左右对应关系。"""

    base_dataset_code: str
    control_dataset_code: str
    mapping: dict[str, Any]


class CompareRoundCreate(BaseModel):
    """启动比较轮次：可覆盖字段映射与两侧数据集，缺省沿用方案登记值。"""

    mapping: dict[str, Any] | None = None
    base_dataset_code: str | None = None
    control_dataset_code: str | None = None
    parent_round_id: int | None = None
    remark: str | None = None


class CompareQuarantineResolution(BaseModel):
    """隔离键组的裁决：确认配对必须显式指定两侧记录，或整组不比较。"""

    decision: str
    base_record_id: str | None = None
    control_record_id: str | None = None
    note: str | None = None


class CompareSignoff(BaseModel):
    note: str | None = None



class QueryEntry(BaseModel):
    """查询语句明细结构。"""

    field_0: str | None = None  # 语句编号
    field_1: str | None = None  # 查询表达式
    field_2: str | None = None  # 目标数据集
    field_3: str | None = None  # 返回字段
    field_4: str | None = None  # 排序条件
    field_5: str | None = None  # 分页大小
    field_6: str | None = None  # 最大行数
    field_7: str | None = None  # 超时秒数

class ChartEntry(BaseModel):
    """图表配置明细结构。"""

    field_0: str | None = None  # 图表编号
    field_1: str | None = None  # 图表名称
    field_2: str | None = None  # 图表类型
    field_3: str | None = None  # 数据来源
    field_4: str | None = None  # X轴字段
    field_5: str | None = None  # Y轴字段
    field_6: str | None = None  # 配色方案
    field_7: str | None = None  # 刷新间隔秒

class SourceEntry(BaseModel):
    """接入配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 连接类型
    field_2: str | None = None  # 接入地址
    field_3: str | None = None  # 认证凭证
    field_4: str | None = None  # 连接池大小
    field_5: str | None = None  # 超时秒数
    field_6: str | None = None  # 重试上限
    field_7: str | None = None  # 负责人

class AggregateEntry(BaseModel):
    """聚合方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 聚合函数
    field_2: str | None = None  # 目标字段
    field_3: str | None = None  # 分组维度
    field_4: str | None = None  # 时间窗口
    field_5: str | None = None  # 筛选条件
    field_6: str | None = None  # 输出精度
    field_7: str | None = None  # 缓存时间

class FilterEntry(BaseModel):
    """筛选规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 目标数据集
    field_2: str | None = None  # 筛选字段
    field_3: str | None = None  # 比较运算符
    field_4: str | None = None  # 比较值
    field_5: str | None = None  # 逻辑组合
    field_6: str | None = None  # 排序字段
    field_7: str | None = None  # 输出行数上限

class ReportgenEntry(BaseModel):
    """报告模板明细结构。"""

    field_0: str | None = None  # 模板编号
    field_1: str | None = None  # 模板名称
    field_2: str | None = None  # 包含图表
    field_3: str | None = None  # 报告周期
    field_4: str | None = None  # 导出格式
    field_5: str | None = None  # 推送渠道
    field_6: str | None = None  # 水印开关
    field_7: str | None = None  # 附件压缩

class AnomalyEntry(BaseModel):
    """检测规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 监控指标
    field_2: str | None = None  # 基线均值
    field_3: str | None = None  # 标准差倍数
    field_4: str | None = None  # 检测周期
    field_5: str | None = None  # 告警级别
    field_6: str | None = None  # 静默窗口分钟
    field_7: str | None = None  # 通知渠道

class DrillEntry(BaseModel):
    """下钻路径明细结构。"""

    field_0: str | None = None  # 路径编号
    field_1: str | None = None  # 起点维度
    field_2: str | None = None  # 下钻层数
    field_3: str | None = None  # 层级维度列表
    field_4: str | None = None  # 聚合指标
    field_5: str | None = None  # 默认展开层
    field_6: str | None = None  # 排序方向
    field_7: str | None = None  # 最多展示行数

class CompareEntry(BaseModel):
    """对比方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 基准数据集
    field_2: str | None = None  # 对照数据集
    field_3: str | None = None  # 对比维度
    field_4: str | None = None  # 对比指标
    field_5: str | None = None  # 差异阈值
    field_6: str | None = None  # 显著性水平
    field_7: str | None = None  # 输出展示

class PipelineEntry(BaseModel):
    """流水线节点明细结构。"""

    field_0: str | None = None  # 节点编号
    field_1: str | None = None  # 节点类型
    field_2: str | None = None  # 输入源
    field_3: str | None = None  # 输出目标
    field_4: str | None = None  # 处理脚本
    field_5: str | None = None  # 依赖上游
    field_6: str | None = None  # 超时秒数
    field_7: str | None = None  # 重试次数

class DatastoreEntry(BaseModel):
    """数据集定义明细结构。"""

    field_0: str | None = None  # 数据集编号
    field_1: str | None = None  # 数据集名称
    field_2: str | None = None  # 来源表名
    field_3: str | None = None  # 字段列表
    field_4: str | None = None  # 更新策略
    field_5: str | None = None  # 数据采样比例
    field_6: str | None = None  # 生命周期天数
    field_7: str | None = None  # 缓存开关

class ForecastEntry(BaseModel):
    """预测模型明细结构。"""

    field_0: str | None = None  # 模型编号
    field_1: str | None = None  # 模型类型
    field_2: str | None = None  # 训练数据集
    field_3: str | None = None  # 目标字段
    field_4: str | None = None  # 特征字段
    field_5: str | None = None  # 预测步长
    field_6: str | None = None  # 置信区间
    field_7: str | None = None  # 评估指标

class SegmentEntry(BaseModel):
    """分片规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 目标数据集
    field_2: str | None = None  # 分片字段
    field_3: str | None = None  # 分片算法
    field_4: str | None = None  # 分片数量
    field_5: str | None = None  # 数据倾斜阈值
    field_6: str | None = None  # 再平衡触发
    field_7: str | None = None  # 迁移策略

class SchedulerEntry(BaseModel):
    """调度配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 调度表达式
    field_3: str | None = None  # 时区设定
    field_4: str | None = None  # 前置任务
    field_5: str | None = None  # 最大并发数
    field_6: str | None = None  # 失败重试策略
    field_7: str | None = None  # 超时终止

class NotifyEntry(BaseModel):
    """通知规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 触发条件
    field_2: str | None = None  # 通知渠道
    field_3: str | None = None  # 接收列表
    field_4: str | None = None  # 消息模板
    field_5: str | None = None  # 合并窗口秒
    field_6: str | None = None  # 重复抑制
    field_7: str | None = None  # 优先级

class CacheEntry(BaseModel):
    """缓存策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标查询
    field_2: str | None = None  # 缓存键规则
    field_3: str | None = None  # 过期秒数
    field_4: str | None = None  # 刷新触发
    field_5: str | None = None  # 命中率阈值
    field_6: str | None = None  # 最大条目数
    field_7: str | None = None  # 淘汰算法

class TagEntry(BaseModel):
    """标签定义明细结构。"""

    field_0: str | None = None  # 标签编号
    field_1: str | None = None  # 标签名称
    field_2: str | None = None  # 计算表达式
    field_3: str | None = None  # 覆盖对象
    field_4: str | None = None  # 更新频率
    field_5: str | None = None  # 标签层级
    field_6: str | None = None  # 值域范围
    field_7: str | None = None  # 失效天数

class ShareEntry(BaseModel):
    """分享链接明细结构。"""

    field_0: str | None = None  # 链接编号
    field_1: str | None = None  # 目标数据集
    field_2: str | None = None  # 访问密码
    field_3: str | None = None  # 有效期天数
    field_4: str | None = None  # 最大浏览次数
    field_5: str | None = None  # 下载开关
    field_6: str | None = None  # 水印内容
    field_7: str | None = None  # 过期自动清理
