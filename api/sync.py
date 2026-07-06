"""
Vercel Cron Job — 每10分钟将故障跟踪表中"备注"有值的行同步到物料跟踪表。

由 vercel.json 中的 crons 配置触发，Vercel 会定时 GET /api/sync。
"""

import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

# Vercel Python runtime 需要把项目根目录加到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tdocs import TdocsClient


# ---- 配置（从环境变量读取） ----

FILE_ID       = os.environ["TDOCS_FILE_ID"]
MASTER_SHEET  = os.environ["TDOCS_MASTER_SHEET_ID"]
TARGET_SHEET  = os.environ["TDOCS_TARGET_SHEET_ID"]
REMARK_COL    = int(os.environ.get("TDOCS_REMARK_COL", "23"))
ORDER_COL     = int(os.environ.get("TDOCS_ORDER_COL", "22"))
TRACKER_COL   = int(os.environ.get("TDOCS_TRACKER_COL", "11"))
SHIP_COL      = int(os.environ.get("TDOCS_SHIP_COL", "4"))

# 物料跟踪表数据起始行（0-based，即第5行）
TARGET_DATA_START_ROW = 4

# 读取范围（一次最多 10000 格）
READ_RANGE = "A3:X301"


def build_client() -> TdocsClient:
    return TdocsClient(
        access_token=os.environ["TDOCS_ACCESS_TOKEN"],
        client_id=os.environ["TDOCS_CLIENT_ID"],
        open_id=os.environ["TDOCS_OPEN_ID"],
    )


def do_sync() -> str:
    client = build_client()

    # 1. 读取总表（故障跟踪表）全部数据行
    master_rows = client.read_range(FILE_ID, MASTER_SHEET, READ_RANGE)
    print(f"[sync] 总表读取 {len(master_rows)} 行")

    # 2. 筛选"备注"列有值的行
    candidates = []
    for row in master_rows:
        if len(row) > REMARK_COL and row[REMARK_COL].strip():
            candidates.append(row)

    print(f"[sync] 备注有值的行数: {len(candidates)}")
    if not candidates:
        return "no candidates"

    # 3. 读取物料跟踪表现有数据，获取已有工单号列表用于去重
    existing = client.read_range(FILE_ID, TARGET_SHEET, "A5:A202")
    existing_orders = []
    for row in existing:
        val = row[0].strip() if row and row[0].strip() else ""
        if val:
            existing_orders.append(val)
    print(f"[sync] 已有物料记录: {len(existing_orders)} 条")

    # 4. 过滤出新行
    new_rows = []
    for row in candidates:
        order_no = row[ORDER_COL].strip() if len(row) > ORDER_COL else ""
        if not order_no:
            continue  # 没有工单号，跳过
        if order_no in existing_orders:
            continue  # 已存在，跳过

        new_rows.append([
            order_no,                        # A: 维修工单
            row[TRACKER_COL].strip(),        # B: 跟踪人
            row[REMARK_COL].strip(),         # C: 维修备件及数量（备注内容）
            "",                               # D: 备件序列号
            "",                               # E: 领料时间
            "",                               # F: 是否退回
            "",                               # G: 退料时间
            "",                               # H: 退回备注
            "",                               # I: 客户
            row[SHIP_COL].strip(),           # J: 船号
        ])

    print(f"[sync] 待写入: {len(new_rows)} 行")

    if not new_rows:
        return "no new rows"

    # 5. 追加写入物料跟踪表
    start_row = TARGET_DATA_START_ROW + len(existing_orders)
    updated = client.write_range(FILE_ID, TARGET_SHEET, start_row, 0, new_rows)
    return f"written {len(new_rows)} rows, {updated} cells"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            msg = do_sync()
            self._respond(200, {"ok": True, "msg": msg})
        except Exception:
            traceback.print_exc()
            self._respond(500, {"ok": False, "error": traceback.format_exc()})

    def _respond(self, status: int, body: dict):
        import json
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)
