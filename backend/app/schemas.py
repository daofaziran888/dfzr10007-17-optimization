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



class MartEntry(BaseModel):
    """集市定义明细结构。"""

    field_0: str | None = None  # 集市编号
    field_1: str | None = None  # 集市名称
    field_2: str | None = None  # 数据源表
    field_3: str | None = None  # 字段选择
    field_4: str | None = None  # 聚合粒度
    field_5: str | None = None  # 刷新策略
    field_6: str | None = None  # 分区字段
    field_7: str | None = None  # 集市状态

class SqlpadEntry(BaseModel):
    """查询脚本明细结构。"""

    field_0: str | None = None  # 脚本编号
    field_1: str | None = None  # 脚本名称
    field_2: str | None = None  # SQL语句
    field_3: str | None = None  # 参数定义
    field_4: str | None = None  # 执行历史
    field_5: str | None = None  # 结果缓存
    field_6: str | None = None  # 创建人
    field_7: str | None = None  # 脚本状态

class VizdragEntry(BaseModel):
    """可视化方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 方案名称
    field_2: str | None = None  # 数据源绑定
    field_3: str | None = None  # 图表类型
    field_4: str | None = None  # 横轴字段
    field_5: str | None = None  # 纵轴字段
    field_6: str | None = None  # 分组字段
    field_7: str | None = None  # 方案状态

class CollabEntry(BaseModel):
    """协作看板明细结构。"""

    field_0: str | None = None  # 看板编号
    field_1: str | None = None  # 看板名称
    field_2: str | None = None  # 协作成员
    field_3: str | None = None  # 图表集合
    field_4: str | None = None  # 刷新频率
    field_5: str | None = None  # 评论开关
    field_6: str | None = None  # 创建时间
    field_7: str | None = None  # 看板状态

class AnomalyEntry(BaseModel):
    """异动记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 指标名称
    field_2: str | None = None  # 异动方向
    field_3: str | None = None  # 异动幅度
    field_4: str | None = None  # 归因维度
    field_5: str | None = None  # 归因结论
    field_6: str | None = None  # 处理建议
    field_7: str | None = None  # 异动时间

class ModelEntry(BaseModel):
    """模型注册明细结构。"""

    field_0: str | None = None  # 模型编号
    field_1: str | None = None  # 模型名称
    field_2: str | None = None  # 模型类型
    field_3: str | None = None  # 训练数据
    field_4: str | None = None  # 评估指标
    field_5: str | None = None  # 模型版本
    field_6: str | None = None  # 部署路径
    field_7: str | None = None  # 模型状态

class OptEntry(BaseModel):
    """优化建议明细结构。"""

    field_0: str | None = None  # 建议编号
    field_1: str | None = None  # 目标查询
    field_2: str | None = None  # 优化类型
    field_3: str | None = None  # 当前耗时
    field_4: str | None = None  # 预计提速
    field_5: str | None = None  # 优化方案
    field_6: str | None = None  # 执行状态
    field_7: str | None = None  # 建议时间

class StoryEntry(BaseModel):
    """故事模板明细结构。"""

    field_0: str | None = None  # 模板编号
    field_1: str | None = None  # 故事标题
    field_2: str | None = None  # 分析主题
    field_3: str | None = None  # 图表序列
    field_4: str | None = None  # 叙述文本
    field_5: str | None = None  # 交互流程
    field_6: str | None = None  # 发布渠道
    field_7: str | None = None  # 模板状态

class EtlEntry(BaseModel):
    """准备任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 任务名称
    field_2: str | None = None  # 输入源
    field_3: str | None = None  # 转换步骤
    field_4: str | None = None  # 输出目标
    field_5: str | None = None  # 调度周期
    field_6: str | None = None  # 依赖关系
    field_7: str | None = None  # 任务状态

class CatalogEntry(BaseModel):
    """目录条目明细结构。"""

    field_0: str | None = None  # 条目编号
    field_1: str | None = None  # 数据集名称
    field_2: str | None = None  # 业务域
    field_3: str | None = None  # 字段清单
    field_4: str | None = None  # 更新频率
    field_5: str | None = None  # 数据等级
    field_6: str | None = None  # 负责人
    field_7: str | None = None  # 条目状态

class SampleEntry(BaseModel):
    """采样配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 数据源名称
    field_2: str | None = None  # 采样算法
    field_3: str | None = None  # 样本比例
    field_4: str | None = None  # 随机种子
    field_5: str | None = None  # 分层字段
    field_6: str | None = None  # 输出表名
    field_7: str | None = None  # 配置状态

class CompareEntry(BaseModel):
    """对比方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 对比指标
    field_2: str | None = None  # 基准周期
    field_3: str | None = None  # 对比周期
    field_4: str | None = None  # 增长阈值
    field_5: str | None = None  # 告警配置
    field_6: str | None = None  # 对比维度
    field_7: str | None = None  # 方案状态

class ExportEntry(BaseModel):
    """导出任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 数据源名称
    field_2: str | None = None  # 导出格式
    field_3: str | None = None  # 字段选择
    field_4: str | None = None  # 筛选条件
    field_5: str | None = None  # 导出上限
    field_6: str | None = None  # 文件大小
    field_7: str | None = None  # 任务状态

class AlarmEntry(BaseModel):
    """告警规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 监控指标
    field_2: str | None = None  # 告警条件
    field_3: str | None = None  # 告警级别
    field_4: str | None = None  # 通知渠道
    field_5: str | None = None  # 静默周期
    field_6: str | None = None  # 生效时段
    field_7: str | None = None  # 规则状态

class RefreshEntry(BaseModel):
    """刷新策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标数据集
    field_2: str | None = None  # 刷新周期
    field_3: str | None = None  # 刷新范围
    field_4: str | None = None  # 增量字段
    field_5: str | None = None  # 全量标记
    field_6: str | None = None  # 下一次刷新
    field_7: str | None = None  # 策略状态

class AuditEntry(BaseModel):
    """审计记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 查询语句
    field_2: str | None = None  # 执行人
    field_3: str | None = None  # 执行耗时
    field_4: str | None = None  # 扫描行数
    field_5: str | None = None  # 返回行数
    field_6: str | None = None  # 执行时间
    field_7: str | None = None  # 复核状态
