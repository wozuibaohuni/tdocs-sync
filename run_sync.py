# 腾讯文档总表 -> 物料跟踪表 自动同步脚本
# 与 GitHub Actions 配合使用：python run_sync.py

import os
import sys

from lib.tdocs import TdocsClient

# ---- 配置 ----
FILE_ID      = os.environ["TDOCS_FILE_ID"]
MASTER_SHEET = os.environ["TDOCS_MASTER_SHEET_ID"]   # 故障跟踪表
TARGET_SHEET = os.environ["TDOCS_TARGET_SHEET_ID"]    # 物料跟踪

REMARK_COL   = int(os.environ.get("TDOCS_REMARK_COL", "23"))
ORDER_COL    = int(os.environ.get("TDOCS_ORDER_COL", "22"))
TRACKER_COL  = int(os.environ.get("TDOCS_TRACKER_COL", "11"))
CUSTOMER_COL = int(os.environ.get("TDOCS_CUSTOMER_COL", "5"))
SHIP_COL     = int(os.environ.get("TDOCS_SHIP_COL", "4"))

DATA_START   = 4  # 物料跟踪表数据行起始（0-based，第5行）
READ_RANGE   = "A3:X301"


def main():
    client = TdocsClient(
        access_token=os.environ["TDOCS_ACCESS_TOKEN"],
        client_id=os.environ["TDOCS_CLIENT_ID"],
        open_id=os.environ["TDOCS_OPEN_ID"],
    )

    master = client.read_range(FILE_ID, MASTER_SHEET, READ_RANGE)
    print(f"总表读取 {len(master)} 行")

    candidates = [r for r in master if len(r) > REMARK_COL and r[REMARK_COL].strip()]
    print(f"备注有值: {len(candidates)} 行")

    if not candidates:
        return

    existing = client.read_range(FILE_ID, TARGET_SHEET, "A5:A202")
    known = {r[0].strip() for r in existing if r and r[0].strip()}
    print(f"已有记录: {len(known)} 条")

    new_rows = []
    for row in candidates:
        order = row[ORDER_COL].strip() if len(row) > ORDER_COL else ""
        if not order or order in known:
            continue
        new_rows.append([
            order,                          # A 维修工单
            row[TRACKER_COL].strip(),       # B 跟踪人
            row[REMARK_COL].strip(),        # C 维修备件及数量（备注内容）
            "",                              # D 备件序列号
            "",                              # E 领料时间
            "",                              # F 是否退回
            "",                              # G 退料时间
            "",                              # H 退回备注
            row[CUSTOMER_COL].strip(),      # I 客户
            row[SHIP_COL].strip(),          # J 船号
        ])

    if not new_rows:
        print("无新增数据")

    start = DATA_START + len(known)
    updated = client.write_range(FILE_ID, TARGET_SHEET, start, 0, new_rows)
    print(f"写入 {len(new_rows)} 行, {updated} 个单元格")


if __name__ == "__main__":
    main()
