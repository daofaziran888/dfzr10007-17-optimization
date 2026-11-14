"""数据故事编排业务规则：图表序列分批校验、断点续做、叙述版本与导出读取口径。

设计要点
--------
1. 图表序列按「图表分片」逐片校验，每个分片记录独立的完成位置与状态，
   一次编排请求只推进一个批次；批次内遇到首个未通过校验的分片即中断，
   已完成分片的叙述文本快照与图表状态原样保留，重试时从失败项恢复。
2. 同一图表分片（以完成位置 position 标识）重复到达时走幂等分支，
   不会再追加第二份叙述文本快照。
3. 同一条故事模板同一时刻只允许一个编排批次推进，按模板加独占锁，
   另一个批次争用时直接返回 409，不排队、不覆盖前一批的进度。
4. 叙述文本按版本归档：历史版本严格按原图表序列保留，新一轮编排产生
   新版本，故事主叙述引用当前完成版本；异常分片不进入导出读取链路。
"""
from __future__ import annotations

import threading
from typing import Any

from app.store import store

MODULE = "story"
REQUIRED_FIELDS = ["模板编号", "故事标题", "分析主题"]
STATUS_ORDER = ["草稿", "编排中", "已发布", "已归档"]
# 发布故事只有在全序列编排完成后才会落到「已发布」；前置校验在 run_action 内完成。
ACTION_RULES = {"发布故事": "已发布", "归档故事": "已归档", "删除故事": "已归档"}
NEGATIVE_ACTIONS = []

# 图表类型白名单：pie（饼图）当前渲染引擎不支持，提交即校验失败，
# 用于复现「第 3 个图表失败、从第 4 个继续」的中断恢复场景。
SUPPORTED_CHART_TYPES = {"bar", "line", "kpi", "area", "scatter", "table"}

# 分片状态
SHARD_PENDING = "待校验"
SHARD_VALID = "已通过"
SHARD_REJECTED = "待重试"
SHARD_ABNORMAL = "异常隔离"
# 同一分片连续两次校验失败后隔离，隔离后游标跳过该分片继续向后推进
ABNORMAL_FAILURE_LIMIT = 2


class StoryLockManager:
    """按故事模板维度的独占锁：保证两个编排批次争用同一模板时只能一个推进。"""

    def __init__(self) -> None:
        self._locks: dict[int, threading.Lock] = {}
        self._guard = threading.Lock()

    def acquire(self, entry_id: int) -> bool:
        with self._guard:
            lock = self._locks.setdefault(entry_id, threading.Lock())
        # 非阻塞争抢：拿不到就立即返回，由调用方给出 409，不排队等待。
        return lock.acquire(blocking=False)

    def release(self, entry_id: int) -> None:
        with self._guard:
            lock = self._locks.get(entry_id)
        if lock is not None:
            lock.release()


story_locks = StoryLockManager()


def _split_chart_sequence(raw: Any) -> list[str]:
    """把图表序列字段拆成有序的图表类型列表，兼容逗号/顿号/空白分隔。"""
    if isinstance(raw, list):
        candidates = [str(item).strip() for item in raw]
    else:
        text = str(raw or "").replace("，", ",").replace("、", ",").replace(";", ",")
        candidates = [part.strip() for part in text.split(",")]
    return [item for item in candidates if item]


def _split_narratives(raw: Any, limit: int) -> list[str]:
    """叙述文本按段拆开，与图表分片按下标对齐；不足或超长时按实际数量处理。"""
    if isinstance(raw, list):
        parts = [str(item).strip() for item in raw]
    else:
        text = str(raw or "").replace("；", "|").replace(";", "|")
        parts = [part.strip() for part in text.split("|")]
    parts = [part for part in parts if part]
    return parts[:limit]


def _ensure_orchestration(entry: dict[str, Any]) -> dict[str, Any]:
    """惰性初始化编排进度结构，历史模板（含种子数据）首次编排时自动补齐。"""
    charts = _split_chart_sequence(entry.get("图表序列"))
    narratives = _split_narratives(entry.get("叙述文本"), len(charts))
    if "编排进度" not in entry or not isinstance(entry.get("编排进度"), list):
        entry["编排进度"] = [
            {
                "position": index,
                "图表类型": chart,
                "状态": SHARD_PENDING,
                "失败次数": 0,
                "叙述快照": None,
                "最近错误": None,
            }
            for index, chart in enumerate(charts)
        ]
    entry.setdefault("编排批次", None)
    entry.setdefault("完成位置", -1)
    entry.setdefault("编排完成", False)
    entry.setdefault("叙述版本号", 0)
    entry.setdefault("叙述版本库", [])
    entry.setdefault("发布叙述版本", None)
    entry.setdefault("发布快照", [])
    # 叙述原文保留为分段列表，便于前端按下标展示；首次初始化时才转换。
    if not isinstance(entry.get("叙述分段"), list):
        entry["叙述分段"] = narratives
    return entry


def _current_narrative_text(entry: dict[str, Any]) -> str:
    """按原序列拼接当前已通过分片的叙述快照，作为故事主叙述文本。"""
    snapshots = [
        shard["叙述快照"]
        for shard in entry.get("编排进度", [])
        if shard.get("状态") == SHARD_VALID and shard.get("叙述快照")
    ]
    return " | ".join(snapshots)


def _seal_version(entry: dict[str, Any]) -> dict[str, Any]:
    """编排全序列处理结束后封存一个叙述版本，历史版本按原序列保留。"""
    version_no = int(entry.get("叙述版本号", 0)) + 1
    version = {
        "版本号": version_no,
        "故事标题": entry.get("故事标题"),
        "序列顺序": [shard["图表类型"] for shard in entry["编排进度"]],
        "叙述快照": [
            {
                "position": shard["position"],
                "图表类型": shard["图表类型"],
                "状态": shard["状态"],
                "叙述文本": shard["叙述快照"],
            }
            for shard in entry["编排进度"]
        ],
        "异常分片": [
            shard["position"]
            for shard in entry["编排进度"]
            if shard["状态"] == SHARD_ABNORMAL
        ],
    }
    entry["叙述版本号"] = version_no
    entry["叙述版本库"].append(version)
    entry["叙述文本"] = _current_narrative_text(entry)
    return version


class StoryService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("模板编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            _ensure_orchestration(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 图表序列与叙述文本允许登记后再补，编排时再做严格校验。
        entry["图表序列"] = values.get("图表序列", "")
        entry["叙述文本"] = values.get("叙述文本", "")
        entry["交互流程"] = values.get("交互流程", "")
        entry["发布渠道"] = values.get("发布渠道", "")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        _ensure_orchestration(entry)
        rows.append(entry)
        return entry, []

    # ------------------------------------------------------------------
    # 分批编排：校验、断点恢复、幂等与模板级互斥
    # ------------------------------------------------------------------
    def orchestrate(
        self,
        entry_id: int,
        batch_id: str,
        shards: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str, int]:
        """提交一个编排批次。

        返回 ``(结果明细, 错误说明, HTTP 状态码)``；状态码 200 表示批次被
        正常处理（可能含校验失败分片），409 表示模板正被另一批次占用，
        404 表示模板不存在，400 表示请求本身不合法。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"故事模板 {entry_id} 不存在或已归档", 404
        if not str(batch_id or "").strip():
            return None, "编排批次缺少批次号 batch_id", 400
        if not shards:
            return None, "编排批次没有可处理的图表分片", 400
        _ensure_orchestration(entry)

        if not story_locks.acquire(entry_id):
            holder = entry.get("编排批次")
            return (
                None,
                f"故事模板 {entry.get('模板编号')} 正被编排批次 {holder} 占用，请等待其结束后重试",
                409,
            )
        entry["编排批次"] = batch_id
        try:
            progress = entry["编排进度"]
            total = len(progress)
            # 先做整批入参校验：任何分片位置非法都整批拒绝，避免批次写到一半被 400 打断。
            for payload in shards:
                position = payload.get("position")
                if not isinstance(position, int) or position < 0 or position >= total:
                    return (
                        None,
                        f"分片完成位置 position 必须落在 0..{total - 1} 之间，收到 {position!r}",
                        400,
                    )
            processed: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            interrupted = False

            for payload in shards:
                position = payload["position"]
                shard = progress[position]

                # 幂等：同位置分片已在本版本处理过（通过/隔离），重复到达直接回放，
                # 不再追加第二份叙述文本快照。
                if shard["状态"] in (SHARD_VALID, SHARD_ABNORMAL):
                    skipped.append(
                        {
                            "position": position,
                            "图表类型": shard["图表类型"],
                            "原因": "分片已处理，重复到达已幂等忽略",
                        }
                    )
                    continue

                # 断点恢复：只能从失败项/待校验项开始，不允许跳过未完成位置。
                expected = entry["完成位置"] + 1
                if position != expected:
                    interrupted = True
                    errors.append(
                        {
                            "position": position,
                            "图表类型": shard["图表类型"],
                            "原因": f"分片乱序：当前应从完成位置 {expected}（下一项）恢复，不能提交 {position}",
                        }
                    )
                    break

                chart_type = str(payload.get("图表类型") or shard["图表类型"] or "").strip()
                narrative = str(payload.get("叙述文本") or "").strip()
                shard["图表类型"] = chart_type

                problems = self._validate_shard(chart_type, narrative)
                if problems:
                    # 校验中断：完成位置保持在失败项之前，已完成分片不受影响。
                    shard["失败次数"] = int(shard.get("失败次数", 0)) + 1
                    shard["最近错误"] = "；".join(problems)
                    if shard["失败次数"] >= ABNORMAL_FAILURE_LIMIT:
                        # 重试仍失败：按失败项重试后仍不通过，隔离异常分片并越过它。
                        shard["状态"] = SHARD_ABNORMAL
                        entry["完成位置"] = position
                        skipped.append(
                            {
                                "position": position,
                                "图表类型": chart_type,
                                "原因": f"连续 {shard['失败次数']} 次校验失败，分片异常隔离，不进入导出：{shard['最近错误']}",
                            }
                        )
                    else:
                        shard["状态"] = SHARD_REJECTED
                        interrupted = True
                        errors.append(
                            {
                                "position": position,
                                "图表类型": chart_type,
                                "原因": shard["最近错误"],
                            }
                        )
                        break
                else:
                    shard["状态"] = SHARD_VALID
                    # 同一位置只保留一份快照：重复到达走上面的幂等分支，
                    # 走到这里的首次写入直接赋值，不存在追加第二份的路径。
                    shard["叙述快照"] = narrative
                    shard["最近错误"] = None
                    entry["完成位置"] = position
                    processed.append(
                        {
                            "position": position,
                            "图表类型": chart_type,
                            "叙述文本": narrative,
                        }
                    )

            completed = entry["完成位置"] >= total - 1
            sealed_version = None
            if completed and not entry.get("编排完成"):
                entry["编排完成"] = True
                sealed_version = _seal_version(entry)
            elif entry.get("编排完成"):
                entry["叙述文本"] = _current_narrative_text(entry)

            # 编排中状态只覆盖草稿阶段；已发布/已归档的故事不被后续批次回退状态。
            if not completed and entry["status"] not in (STATUS_ORDER[2], STATUS_ORDER[3]):
                entry["status"] = STATUS_ORDER[1]
            entry["pending"] = not completed
            entry["abnormal"] = any(
                shard["状态"] == SHARD_ABNORMAL for shard in progress
            )
            result = {
                "模板编号": entry.get("模板编号"),
                "批次号": batch_id,
                "完成位置": entry["完成位置"],
                "序列长度": total,
                "编排完成": bool(entry.get("编排完成")),
                "中断": interrupted,
                "本批通过": processed,
                "幂等忽略": skipped,
                "校验失败": errors,
                "编排进度": [dict(shard) for shard in progress],
                "封存版本": sealed_version,
                "叙述版本号": entry.get("叙述版本号"),
            }
            return result, "", 200
        finally:
            entry["编排批次"] = None
            story_locks.release(entry_id)

    @staticmethod
    def _validate_shard(chart_type: str, narrative: str) -> list[str]:
        problems: list[str] = []
        if not chart_type:
            problems.append("图表类型为空")
        elif chart_type not in SUPPORTED_CHART_TYPES:
            problems.append(f"图表类型 {chart_type} 不在支持范围 {sorted(SUPPORTED_CHART_TYPES)} 内")
        if not narrative:
            problems.append("叙述文本快照为空")
        return problems

    def reset_orchestration(
        self, entry_id: int, batch_id: str
    ) -> tuple[dict[str, Any] | None, str, int]:
        """开启新一轮编排：历史叙述版本按原序列封存保留，新版本重新引用新叙述。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"故事模板 {entry_id} 不存在或已归档", 404
        if not str(batch_id or "").strip():
            return None, "编排批次缺少批次号 batch_id", 400
        _ensure_orchestration(entry)

        if not story_locks.acquire(entry_id):
            return (
                None,
                f"故事模板 {entry.get('模板编号')} 正被编排批次 {entry.get('编排批次')} 占用，请等待其结束后重试",
                409,
            )
        entry["编排批次"] = batch_id
        try:
            # 未封存过的开放版本先归档，保证历史版本不丢、序列顺序不变。
            if not entry.get("编排完成") and any(
                shard["状态"] != SHARD_PENDING for shard in entry["编排进度"]
            ):
                _seal_version(entry)
            charts = [shard["图表类型"] for shard in entry["编排进度"]]
            entry["编排进度"] = [
                {
                    "position": index,
                    "图表类型": chart,
                    "状态": SHARD_PENDING,
                    "失败次数": 0,
                    "叙述快照": None,
                    "最近错误": None,
                }
                for index, chart in enumerate(charts)
            ]
            entry["完成位置"] = -1
            entry["编排完成"] = False
            entry["pending"] = True
            entry["abnormal"] = False
            entry["status"] = STATUS_ORDER[1]
            return {
                "模板编号": entry.get("模板编号"),
                "批次号": batch_id,
                "历史版本数": len(entry.get("叙述版本库", [])),
                "下一轮版本号": int(entry.get("叙述版本号", 0)) + 1,
                "编排进度": [dict(shard) for shard in entry["编排进度"]],
            }, "", 200
        finally:
            entry["编排批次"] = None
            story_locks.release(entry_id)

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"故事模板 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据故事编排可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        if action == "发布故事":
            _ensure_orchestration(entry)
            if not entry["编排进度"]:
                return None, "图表序列为空，没有可校验的图表分片，不能发布"
            if not entry.get("编排完成"):
                pending = [
                    shard["position"]
                    for shard in entry["编排进度"]
                    if shard["状态"] in (SHARD_PENDING, SHARD_REJECTED)
                ]
                return (
                    None,
                    f"故事尚未完成全序列编排，未完成分片位置 {pending}，不能发布",
                )
            valid_snapshots = [
                shard["叙述快照"]
                for shard in entry["编排进度"]
                if shard["状态"] == SHARD_VALID and shard.get("叙述快照")
            ]
            if not valid_snapshots:
                return None, "没有任何通过校验的图表分片，缺少可发布的叙述内容，不能发布"

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS

        if action == "发布故事":
            # 发布快照引用当前叙述版本；异常分片已被排除在叙述快照之外。
            entry["发布叙述版本"] = entry.get("叙述版本号")
            entry["发布快照"] = [
                {
                    "position": shard["position"],
                    "图表类型": shard["图表类型"],
                    "叙述文本": shard["叙述快照"],
                }
                for shard in entry["编排进度"]
                if shard["状态"] == SHARD_VALID
            ]
            entry["叙述文本"] = " | ".join(
                item["叙述文本"] for item in entry["发布快照"]
            )
        return entry, f"故事模板已{action}"

    # ------------------------------------------------------------------
    # 导出读取链路：只放完整故事，异常分片不进入，空结果说明缺失原因
    # ------------------------------------------------------------------
    def export_stories(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for entry in store.rows(MODULE):
            _ensure_orchestration(entry)
            progress = entry.get("编排进度", [])
            abnormal_positions = [
                shard["position"] for shard in progress if shard["状态"] == SHARD_ABNORMAL
            ]
            if not entry.get("编排完成"):
                pending = [
                    shard["position"]
                    for shard in progress
                    if shard["状态"] in (SHARD_PENDING, SHARD_REJECTED)
                ]
                excluded.append(
                    {
                        "模板编号": entry.get("模板编号"),
                        "原因": f"编排未完成，缺失分片位置 {pending}，数据故事清单不收录未完成故事",
                    }
                )
                continue
            valid = [
                shard for shard in progress if shard["状态"] == SHARD_VALID
            ]
            if not valid:
                excluded.append(
                    {
                        "模板编号": entry.get("模板编号"),
                        "原因": "全部分片异常隔离，没有可导出的叙述内容",
                    }
                )
                continue
            # 导出严格按原图表序列输出，异常分片剔除并在说明里点名。
            items.append(
                {
                    "模板编号": entry.get("模板编号"),
                    "故事标题": entry.get("故事标题"),
                    "分析主题": entry.get("分析主题"),
                    "引用叙述版本": entry.get("叙述版本号"),
                    "发布叙述版本": entry.get("发布叙述版本"),
                    "故事状态": entry.get("status"),
                    "图表序列": [shard["图表类型"] for shard in progress],
                    "叙述分片": [
                        {
                            "position": shard["position"],
                            "图表类型": shard["图表类型"],
                            "叙述文本": shard["叙述快照"],
                        }
                        for shard in valid
                    ],
                    "异常分片位置": abnormal_positions,
                    "缺失说明": (
                        f"位置 {abnormal_positions} 的分片校验失败已隔离，不进入导出"
                        if abnormal_positions
                        else ""
                    ),
                }
            )

        if items:
            message = "数据故事清单已生成，异常分片已剔除并在缺失说明中标注"
        else:
            reasons = "；".join(
                f"{row['模板编号']}：{row['原因']}" for row in excluded
            ) or "当前没有任何故事模板"
            message = f"暂无数据可导出：{reasons}"
        return {
            "module": "story",
            "total": len(items),
            "items": items,
            "excluded": excluded,
            "message": message,
        }
