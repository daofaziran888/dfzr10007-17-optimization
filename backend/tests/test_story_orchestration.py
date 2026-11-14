"""STOR-0002 分批校验/断点恢复/叙述版本/导出读取链路的端到端核对脚本。

只依赖标准库：直接调用 service 层验证业务规则，再起真实 uvicorn 进程
用 urllib 核对 HTTP 链路（含 400/404/409 状态码）。

运行：.venv/bin/python -I tests/test_story_orchestration.py
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.story import (  # noqa: E402
    ABNORMAL_FAILURE_LIMIT,
    SHARD_ABNORMAL,
    SHARD_PENDING,
    SHARD_REJECTED,
    SHARD_VALID,
    story_locks,
)
from app.services.story import StoryService  # noqa: E402
from app.store import store  # noqa: E402

service = StoryService()
PASS = []
FAIL = []


def check(name: str, condition: bool, detail: object = None) -> None:
    if condition:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append((name, detail))
        print(f"  ❌ {name} -> {detail}")


def shard(position: int, chart: str, narrative: str) -> dict:
    return {"position": position, "图表类型": chart, "叙述文本": narrative}


def find_story(code: str) -> dict:
    for row in store.rows("story"):
        if row.get("模板编号") == code:
            service.get_entry(row["id"])  # 触发惰性编排结构初始化
            return row
    raise AssertionError(f"种子数据缺少 {code}")


print("== 场景 0：STOR-0002 种子数据（标题/叙述/序列） ==")
entry = find_story("STOR-0002")
entry_id = entry["id"]
check("故事标题为区域销售转化复盘故事", entry["故事标题"] == "区域销售转化复盘故事", entry["故事标题"])
original_narratives = list(entry["叙述分段"])
check("叙述文本拆成 4 段且与图表序列对齐", len(original_narratives) == 4, original_narratives)
check("图表序列为 bar、line、pie、kpi", [s["图表类型"] for s in entry["编排进度"]] == ["bar", "line", "pie", "kpi"])
check("初始四个分片均待校验", all(s["状态"] == SHARD_PENDING for s in entry["编排进度"]))
check("初始完成位置为 -1", entry["完成位置"] == -1)

print("== 场景 1：批次 B1 分批提交，前两个分片通过 ==")
r, msg, code = service.orchestrate(entry_id, "B1", [shard(0, "bar", original_narratives[0])])
check("bar 分片通过", code == 200 and r["编排进度"][0]["状态"] == SHARD_VALID, r)
check("完成位置推进到 0", r["完成位置"] == 0, r["完成位置"])
bar_snapshot_v1 = r["编排进度"][0]["叙述快照"]

r, _, code = service.orchestrate(entry_id, "B1", [shard(1, "line", original_narratives[1])])
check("line 分片通过", code == 200 and r["编排进度"][1]["状态"] == SHARD_VALID, r)
check("完成位置推进到 1", r["完成位置"] == 1, r["完成位置"])
line_snapshot_v1 = r["编排进度"][1]["叙述快照"]

print("== 场景 2：第 3 个分片 pie 校验失败，中断且不影响前序分片 ==")
r, _, code = service.orchestrate(entry_id, "B1", [shard(2, "pie", original_narratives[2])])
check("pie 失败返回 200（批次被处理但含失败项）", code == 200, code)
check("本批记录 1 条校验失败且中断", len(r["校验失败"]) == 1 and r["中断"] is True, r["校验失败"])
check("失败原因指明 pie 不在支持范围", "pie" in r["校验失败"][0]["原因"], r["校验失败"])
check("pie 分片状态为待重试", r["编排进度"][2]["状态"] == SHARD_REJECTED, r["编排进度"][2])
check("完成位置停在 1（失败项不推进）", r["完成位置"] == 1, r["完成位置"])
check("pie 没有写入任何叙述快照", r["编排进度"][2]["叙述快照"] is None)
check("bar 叙述分片未被重写", r["编排进度"][0]["叙述快照"] == bar_snapshot_v1 == original_narratives[0])
check("line 叙述分片未被重写", r["编排进度"][1]["叙述快照"] == line_snapshot_v1 == original_narratives[1])

print("== 场景 3：按失败项重试 pie，仍失败后异常隔离，再从 kpi 继续 ==")
r, _, code = service.orchestrate(entry_id, "B2-RETRY", [shard(2, "pie", original_narratives[2])])
check(f"连续 {ABNORMAL_FAILURE_LIMIT} 次失败后 pie 被异常隔离",
      code == 200 and r["编排进度"][2]["状态"] == SHARD_ABNORMAL, r["编排进度"][2])
check("隔离后完成位置越过 pie 到 2", r["完成位置"] == 2, r["完成位置"])
check("隔离分片仍无叙述快照", r["编排进度"][2]["叙述快照"] is None)

r, _, code = service.orchestrate(entry_id, "B3", [shard(3, "kpi", original_narratives[3])])
check("从第 4 个分片 kpi 恢复并通过", code == 200 and r["编排进度"][3]["状态"] == SHARD_VALID, r)
check("全序列处理完成并封存叙述版本 v1", r["编排完成"] is True and r["封存版本"] is not None
      and r["封存版本"]["版本号"] == 1, r)
check("版本库按原序列 bar/line/pie/kpi 保留",
      r["封存版本"]["序列顺序"] == ["bar", "line", "pie", "kpi"], r["封存版本"]["序列顺序"])
check("版本 v1 记录异常分片位置 2", r["封存版本"]["异常分片"] == [2])

print("== 场景 4：同一图表分片再次到达，幂等不追加第二份叙述快照 ==")
r, _, code = service.orchestrate(entry_id, "B4-DUP", [shard(0, "bar", original_narratives[0])])
check("重复 bar 分片被幂等忽略", code == 200 and len(r["幂等忽略"]) == 1
      and r["幂等忽略"][0]["position"] == 0, r["幂等忽略"])
check("bar 快照仍只有一份且内容不变",
      entry["编排进度"][0]["叙述快照"] == original_narratives[0])
snapshots_v1 = [s for s in entry["编排进度"] if s["叙述快照"]]
check("全序列叙述快照恰好 3 份（bar/line/kpi）", len(snapshots_v1) == 3, len(snapshots_v1))

print("== 场景 5：两个编排批次争用同一模板，只能一个推进 ==")
got_lock = threading.Event()
release_lock = threading.Event()

def hold_lock() -> None:
    story_locks.acquire(entry_id)
    got_lock.set()
    release_lock.wait(timeout=5)
    story_locks.release(entry_id)

holder = threading.Thread(target=hold_lock)
holder.start()
got_lock.wait(timeout=2)
r, msg, code = service.orchestrate(entry_id, "B5-CONTEND", [shard(0, "bar", original_narratives[0])])
check("争用批次被拒绝且返回 409", code == 409 and r is None, (code, msg))
check("409 信息提示模板被占用", "占用" in msg, msg)
release_lock.set()
holder.join()
r, _, code = service.orchestrate(entry_id, "B5-AFTER", [shard(0, "bar", original_narratives[0])])
check("锁释放后批次可正常推进（仍走幂等）", code == 200 and len(r["幂等忽略"]) == 1, code)

print("== 场景 6：乱序分片必须从失败项/下一项恢复 ==")
fresh = service.create_entry({
    "模板编号": "STOR-0099",
    "故事标题": "乱序校验故事",
    "分析主题": "恢复顺序核对",
    "图表序列": "bar,line",
    "叙述文本": "第一段 | 第二段",
})[0]
r, msg, code = service.orchestrate(fresh["id"], "B-OOO", [shard(1, "line", "第二段")])
check("跳过 position 0 直接提交 1 被批次中断拦下",
      code == 200 and r["中断"] is True and r["校验失败"][0]["position"] == 1, (code, r))
check("错误说明应从完成位置 0 恢复", "应从完成位置 0" in r["校验失败"][0]["原因"], r)
check("乱序分片不推进完成位置", fresh["完成位置"] == -1, fresh["完成位置"])
r, _, code = service.orchestrate(fresh["id"], "B-OOO", [shard(0, "bar", "第一段")])
check("按正确位置 0 提交可通过", code == 200 and r["编排进度"][0]["状态"] == SHARD_VALID)

print("== 场景 6b：单批次携带多个分片，失败项后同批继续推进 ==")
multi = service.create_entry({
    "模板编号": "STOR-0097",
    "故事标题": "多分片批次故事",
    "分析主题": "批次粒度核对",
    "图表序列": "bar,pie,kpi",
    "叙述文本": "第一段 | 第二段 | 第三段",
})[0]
r, _, code = service.orchestrate(multi["id"], "B-MULTI", [
    shard(0, "bar", "第一段"),
    shard(1, "pie", "第二段"),
    shard(2, "kpi", "第三段"),
])
check("多分片批次返回 200 且在 pie 处标记中断", code == 200 and r["中断"] is True, r)
check("批次内 bar 已通过、pie 待重试、kpi 未被越过",
      [s["状态"] for s in r["编排进度"]] == [SHARD_VALID, SHARD_REJECTED, SHARD_PENDING],
      r["编排进度"])
r, _, code = service.orchestrate(multi["id"], "B-MULTI-RETRY", [
    shard(1, "pie", "第二段"),
    shard(2, "kpi", "第三段"),
])
check("重试批次内 pie 二次失败隔离后 kpi 同批通过并封存版本",
      code == 200 and r["编排完成"] is True
      and [s["状态"] for s in r["编排进度"]] == [SHARD_VALID, SHARD_ABNORMAL, SHARD_VALID]
      and r["封存版本"]["异常分片"] == [1], r)

print("== 场景 7：发布故事引用当前叙述版本，异常分片不进入发布结果 ==")
published, message = service.run_action(entry_id, "发布故事")
check("发布成功", published is not None, message)
check("发布引用叙述版本 v1", published["发布叙述版本"] == 1, published["发布叙述版本"])
check("发布快照只含 bar/line/kpi 三个分片",
      [s["position"] for s in published["发布快照"]] == [0, 1, 3], published["发布快照"])
check("发布主叙述由三段快照按原序列拼接",
      published["叙述文本"] == " | ".join(original_narratives[:2] + original_narratives[3:]),
      published["叙述文本"])
check("发布后故事状态为已发布", published["status"] == "已发布")

blocked, message = service.run_action(fresh["id"], "发布故事")
check("未完成编排的故事禁止发布", blocked is None and "不能发布" in message, message)

print("== 场景 8：导出读取链路——完整故事收录、异常分片剔除、空结果说明原因 ==")
exported = service.export_stories()
story0002 = next((item for item in exported["items"] if item["模板编号"] == "STOR-0002"), None)
check("STOR-0002 进入数据故事清单", story0002 is not None)
check("导出引用叙述版本 v1", story0002 and story0002["引用叙述版本"] == 1)
check("导出叙述分片严格按原序列且只有 3 片",
      story0002 and [s["position"] for s in story0002["叙述分片"]] == [0, 1, 3])
check("导出点名异常分片位置 2 并给出缺失说明",
      story0002 and story0002["异常分片位置"] == [2] and "位置 [2]" in story0002["缺失说明"])
check("导出中 bar/line 叙述仍是原始前两段（未重写）",
      story0002 and story0002["叙述分片"][0]["叙述文本"] == original_narratives[0]
      and story0002["叙述分片"][1]["叙述文本"] == original_narratives[1])
excluded_codes = {row["模板编号"] for row in exported["excluded"]}
check("未完成的 STOR-0099 不进入导出", "STOR-0099" in excluded_codes, excluded_codes)
reason_0099 = next(row["原因"] for row in exported["excluded"] if row["模板编号"] == "STOR-0099")
check("缺失原因写明未完成分片位置", "缺失分片位置 [1]" in reason_0099, reason_0099)

all_fail = service.create_entry({
    "模板编号": "STOR-0098",
    "故事标题": "全异常故事",
    "分析主题": "空结果核对",
    "图表序列": "pie",
    "叙述文本": "唯一一段",
})[0]
for attempt in range(ABNORMAL_FAILURE_LIMIT):
    service.orchestrate(all_fail["id"], f"B-FAIL-{attempt}", [shard(0, "pie", "唯一一段")])
exported2 = service.export_stories()
check("全异常故事不进入导出", all(item["模板编号"] != "STOR-0098" for item in exported2["items"]))
reason_0098 = next(row["原因"] for row in exported2["excluded"] if row["模板编号"] == "STOR-0098")
check("空结果原因说明全部分片异常隔离", "全部分片异常隔离" in reason_0098, reason_0098)

print("== 场景 9：新一轮编排——历史版本按原序列保留，新版本引用新叙述 ==")
r, msg, code = service.reset_orchestration(entry_id, "B-RESET")
check("重置成功并保留 1 个历史版本", code == 200 and r["历史版本数"] == 1, (code, msg, r))
check("新一轮分片全部回到待校验、完成位置归零",
      all(s["状态"] == SHARD_PENDING for s in r["编排进度"]) and entry["完成位置"] == -1)
v1_archive = entry["叙述版本库"][0]
check("历史版本 v1 仍按原序列保留原始前两段叙述",
      v1_archive["序列顺序"] == ["bar", "line", "pie", "kpi"]
      and v1_archive["叙述快照"][0]["叙述文本"] == original_narratives[0]
      and v1_archive["叙述快照"][1]["叙述文本"] == original_narratives[1])

new_texts = ["新版柱状图叙述", "新版折线图叙述", "新版饼图叙述", "新版KPI叙述"]
service.orchestrate(entry_id, "N1", [shard(0, "bar", new_texts[0])])
service.orchestrate(entry_id, "N2", [shard(1, "line", new_texts[1])])
service.orchestrate(entry_id, "N3", [shard(2, "pie", new_texts[2])])
service.orchestrate(entry_id, "N4", [shard(2, "pie", new_texts[2])])
r, _, _ = service.orchestrate(entry_id, "N5", [shard(3, "kpi", new_texts[3])])
check("新一轮封存版本 v2", r["封存版本"] is not None and r["封存版本"]["版本号"] == 2)
check("版本库共 2 个版本且 v1 内容未被覆盖",
      len(entry["叙述版本库"]) == 2
      and entry["叙述版本库"][0]["叙述快照"][3]["叙述文本"] == original_narratives[3]
      and entry["叙述版本库"][1]["叙述快照"][3]["叙述文本"] == new_texts[3])
published, _ = service.run_action(entry_id, "发布故事")
check("再次发布引用新版本 v2", published["发布叙述版本"] == 2, published["发布叙述版本"])
check("发布快照使用新版叙述文本",
      published["发布快照"][0]["叙述文本"] == new_texts[0], published["发布快照"])

exported3 = service.export_stories()
story0002_v2 = next(item for item in exported3["items"] if item["模板编号"] == "STOR-0002")
check("导出清单切换引用新版本 v2", story0002_v2["引用叙述版本"] == 2, story0002_v2)
check("导出清单标题与叙述均为新版内容",
      story0002_v2["故事标题"] == "区域销售转化复盘故事"
      and story0002_v2["叙述分片"][0]["叙述文本"] == new_texts[0])

print("== 场景 10：HTTP 链路（真实 uvicorn + urllib） ==")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8123"],
    cwd=Path(__file__).resolve().parents[1],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)


def http(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:8123{path}", data=data,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


try:
    for _ in range(50):
        try:
            status, body = http("GET", "/api/health")
            if status == 200:
                break
        except Exception:
            time.sleep(0.2)
    check("健康检查 200", status == 200 and body.get("ok") is True, body)

    status, body = http("GET", "/api/story/2/orchestration")
    check("GET 编排进度 200 且序列为 bar/line/pie/kpi",
          status == 200 and [s["图表类型"] for s in body["编排进度"]] == ["bar", "line", "pie", "kpi"], body)

    status, body = http("POST", "/api/story/2/orchestration",
                        {"batch_id": "H1", "shards": [{"position": 0, "图表类型": "bar", "叙述文本": "HTTP柱状图叙述"}]})
    check("HTTP 分批提交 bar 成功", status == 200 and body["ok"] is True
          and body["entry"]["完成位置"] == 0, body)

    status, body = http("POST", "/api/story/2/orchestration",
                        {"batch_id": "H2", "shards": [{"position": 3, "图表类型": "kpi", "叙述文本": "乱序"}]})
    check("HTTP 乱序分片以批次中断返回并提示从完成位置 1 恢复",
          status == 200 and body["entry"]["中断"] is True
          and "应从完成位置 1" in body["entry"]["校验失败"][0]["原因"], body)

    status, body = http("POST", "/api/story/999/orchestration",
                        {"batch_id": "H3", "shards": [{"position": 0, "图表类型": "bar", "叙述文本": "x"}]})
    check("HTTP 不存在模板返回 404", status == 404, body)

    status, body = http("POST", "/api/story/2/orchestration",
                        {"batch_id": "H4", "shards": [{"position": 1, "图表类型": "pie", "叙述文本": "饼图"}]})
    check("HTTP pie 失败被批次结果标记（中断可恢复）",
          status == 200 and body["entry"]["中断"] is True
          and body["entry"]["编排进度"][1]["状态"] == SHARD_REJECTED, body)

    status, body = http("GET", "/api/story/export")
    check("HTTP 导出 200 且未完成故事被排除并附原因",
          status == 200 and any(row["模板编号"] == "STOR-0002" for row in body["excluded"]), body)
    check("HTTP 空结果时 total=0 且 message 说明缺失原因",
          body["total"] == 0 and body["message"].startswith("暂无数据可导出"), body.get("message"))
finally:
    proc.terminate()
    proc.wait(timeout=10)

print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    for name, detail in FAIL:
        print(f"FAILED: {name} -> {detail}")
    sys.exit(1)
print("全部核对通过 ✅")
