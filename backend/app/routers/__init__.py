"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import mart as router_mart
from app.routers import sqlpad as router_sqlpad
from app.routers import vizdrag as router_vizdrag
from app.routers import collab as router_collab
from app.routers import anomaly as router_anomaly
from app.routers import model as router_model
from app.routers import opt as router_opt
from app.routers import story as router_story
from app.routers import etl as router_etl
from app.routers import catalog as router_catalog
from app.routers import sample as router_sample
from app.routers import compare as router_compare
from app.routers import export as router_export
from app.routers import alarm as router_alarm
from app.routers import refresh as router_refresh
from app.routers import audit as router_audit

ROUTERS = [router_mart, router_sqlpad, router_vizdrag, router_collab, router_anomaly, router_model, router_opt, router_story, router_etl, router_catalog, router_sample, router_compare, router_export, router_alarm, router_refresh, router_audit]
