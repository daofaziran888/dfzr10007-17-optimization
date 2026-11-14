"""数据故事编排接口：维护故事模板，覆盖分批编排、断点恢复、发布故事与导出读取。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    EntryPayload,
    OrchestrationPayload,
    OrchestrationResetPayload,
    PageResult,
)
from app.services.story import StoryService

router = APIRouter(prefix="/api/story", tags=["数据故事编排"])

service = StoryService()

LIST_FIELDS = ["模板编号", "故事标题", "分析主题", "图表序列", "叙述文本", "交互流程", "发布渠道", "模板状态"]
STATUSES = ["草稿", "编排中", "已发布", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按模板编号检索"),
    status: str | None = Query(default=None, description="草稿、编排中、已发布、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按模板编号与状态过滤数据故事编排列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出数据故事清单：只收录编排完整的故事，异常分片剔除并说明缺失原因。"""
    return service.export_stories()


@router.get("/{entry_id}/orchestration", response_model=dict)
def get_orchestration(entry_id: int) -> dict[str, Any]:
    """读取编排进度：分片状态、完成位置与叙述版本库，供失败后定位恢复点。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"故事模板 {entry_id} 不存在或已归档")
    return {
        "模板编号": entry.get("模板编号"),
        "故事标题": entry.get("故事标题"),
        "完成位置": entry.get("完成位置"),
        "编排完成": entry.get("编排完成"),
        "叙述版本号": entry.get("叙述版本号"),
        "发布叙述版本": entry.get("发布叙述版本"),
        "占用批次": entry.get("编排批次"),
        "叙述分段": entry.get("叙述分段"),
        "编排进度": entry.get("编排进度"),
        "叙述版本库": entry.get("叙述版本库"),
    }


@router.post("/{entry_id}/orchestration", response_model=ActionResult)
def orchestrate(entry_id: int, payload: OrchestrationPayload) -> ActionResult:
    """分批提交图表分片校验；中断后按失败项重试，重复分片幂等不重复写快照。"""
    shards = [shard.model_dump() for shard in payload.shards]
    result, message, code = service.orchestrate(entry_id, payload.batch_id, shards)
    if result is None:
        # 409 表示另一批次正在推进同一模板，调用方应稍后重试而不是改写数据。
        raise HTTPException(status_code=code, detail=message)
    interrupted = bool(result.get("中断") or result.get("校验失败"))
    summary = (
        "编排批次处理完成，图表序列已全部处理"
        if result.get("编排完成")
        else "编排批次中断，已保留完成位置，可从失败项重试恢复"
        if interrupted
        else "编排批次已接收，完成位置已推进"
    )
    return ActionResult(ok=True, message=summary, entry=result)


@router.post("/{entry_id}/orchestration/reset", response_model=ActionResult)
def reset_orchestration(entry_id: int, payload: OrchestrationResetPayload) -> ActionResult:
    """开启新一轮编排：历史叙述版本按原序列保留，新版本引用新一轮叙述快照。"""
    result, message, code = service.reset_orchestration(entry_id, payload.batch_id)
    if result is None:
        raise HTTPException(status_code=code, detail=message)
    return ActionResult(ok=True, message="已开启新一轮编排，历史叙述版本已归档保留", entry=result)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条故事模板明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"故事模板 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条故事模板，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="故事模板已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条故事模板执行发布故事、归档故事、删除故事；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
