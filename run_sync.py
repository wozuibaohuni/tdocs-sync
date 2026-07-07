# 腾讯文档总表 -> 物料跟踪表 自动同步脚本
# 根据"领料"(col 24)列有值的数据行同步

import os
import sys

from lib.tdocs import TdocsClient

FILE_ID      = os.environ["TDOCS_FILE_ID"]
MASTER_SHEET = os.environ["TDOCS_MASTER_SHEET_ID"]
TARGET_SHEET = os.environ["TDOCS_TARGET_SHEET_ID"]

# 筛选条件：领料列
PICK_COL     = int(os.environ.get("TDOCS_PICK_COL", "24"))

# 数据列
ORDER_COL    = int(os.environ.get("TDOCS_ORDER_COL", "22"))
TRACKER_COL  = int(os.environ.get("TDOCS_TRACKER_COL", "11"))
CUSTOMER_COL = int(os.environ.get("TDOCS_CUSTOMER_COL", "5"))
SHIP_COL     = int(os.environ.get("TDOCS_SHIP_COL", "4"))

DATA_START   = 4
READ_RANGE   = "A3:Y301"   # A-Y = 25 cols (包含 col 24 领料)


def main():
    client = TdocsClient(
        access_token=os.environ["TDOCS_ACCESS_TOKEN"],
        client_id=os.environ["TDOCS_CLIENT_ID"],
        open_id=os.environ["TDOCS_OPEN_ID"],
    )

    master = client.read_range(FILE_ID, MASTER_SHEET, READ_RANGE)
    print(f"总表读取 {len(master)} 行")

    # 筛选领料有值的行
    candidates = [r for r in master if len(r) > PICK_COL and r[PICK_COL].strip()]
    print(f"领料有值: {len(candidates)} 行")

    if not candidates:
        return

    # 读取物料跟踪现有数据
    existing = client.read_range(FILE_ID, TARGET_SHEET, f"A5:J202")

    def row_fingerprint(row):
        order = row[0].strip() if row and row[0].strip() else ""
        if order:
            return ("order", order)
        ship = row[9].strip() if len(row) > 9 and row[9].strip() else ""
        pick = row[2].strip() if len(row) > 2 and row[2].strip() else ""
        return ("no_order", f"{ship}|{pick[:20]}")

    existing_map = {}
    for i, row in enumerate(existing):
        fp = row_fingerprint(row)
        existing_map[fp] = (DATA_START + i, row[:10])

    print(f"已有记录: {len(existing_map)} 条")

    new_rows = []
    update_rows = []

    for master_idx, row in enumerate(candidates):
        order   = row[ORDER_COL].strip()   if len(row) > ORDER_COL else ""
        ship    = row[SHIP_COL].strip()    if len(row) > SHIP_COL else ""
        tracker = row[TRACKER_COL].strip() if len(row) > TRACKER_COL else ""
        cust    = row[CUSTOMER_COL].strip() if len(row) > CUSTOMER_COL else ""
        pick    = row[PICK_COL].strip()    if len(row) > PICK_COL else ""

        new_data = [
            order if order else f"(无工单-{master_idx+3})",  # A 维修工单
            tracker,                                          # B 跟踪人
            pick,                                             # C 维修备件及数量 ← 领料内容
            "",                                                # D 备件序列号
            "",                                                # E 领料时间
            "",                                                # F 是否退回
            "",                                                # G 退料时间
            "",                                                # H 退回备注
            cust,                                             # I 客户
            ship,                                             # J 船号
        ]

        if order:
            fp = ("order", order)
        else:
            fp = ("no_order", pick[:20])

        if fp in existing_map:
            old_pick = existing_map[fp][1][2].strip() if len(existing_map[fp][1]) > 2 else ""
            if old_pick != pick:
                update_rows.append((existing_map[fp][0], new_data))
        else:
            new_rows.append(new_data)

    if new_rows:
        start = DATA_START + len(existing_map)
        updated = client.write_range(FILE_ID, TARGET_SHEET, start, 0, new_rows)
        print(f"新增 {len(new_rows)} 行, {updated} 个单元格")

    for row_num, data in update_rows:
        updated = client.write_range(FILE_ID, TARGET_SHEET, row_num, 0, [data])
        print(f"更新 Row {row_num+1}: {data[0][:30]} ({updated} cells)")

    if not new_rows and not update_rows:
        print("无变化")


if __name__ == "__main__":
    main()
