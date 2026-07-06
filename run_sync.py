# 腾讯文档总表 -> 物料跟踪表 自动同步脚本
# 与 GitHub Actions 配合使用：python run_sync.py

import os
import sys

from lib.tdocs import TdocsClient

FILE_ID      = os.environ["TDOCS_FILE_ID"]
MASTER_SHEET = os.environ["TDOCS_MASTER_SHEET_ID"]
TARGET_SHEET = os.environ["TDOCS_TARGET_SHEET_ID"]

REMARK_COL   = int(os.environ.get("TDOCS_REMARK_COL", "23"))
ORDER_COL    = int(os.environ.get("TDOCS_ORDER_COL", "22"))
TRACKER_COL  = int(os.environ.get("TDOCS_TRACKER_COL", "11"))
CUSTOMER_COL = int(os.environ.get("TDOCS_CUSTOMER_COL", "5"))
SHIP_COL     = int(os.environ.get("TDOCS_SHIP_COL", "4"))

DATA_START   = 4
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

    # 读取物料跟踪现有数据
    existing = client.read_range(FILE_ID, TARGET_SHEET, f"A5:J202")

    # 建立去重索引：
    #   - 有工单号的行 -> 用工单号
    #   - 无工单号的行 -> 用 "船号|备注前20字" 作指纹
    def row_fingerprint(row):
        order = row[0].strip() if row and row[0].strip() else ""
        if order:
            return ("order", order)
        # 无工单号时用船号+备注片段做指纹
        ship = row[9].strip() if len(row) > 9 and row[9].strip() else ""
        remark = row[2].strip() if len(row) > 2 and row[2].strip() else ""
        return ("no_order", f"{ship}|{remark[:20]}")

    existing_map = {}  # fingerprint -> (row_index, old_values)
    for i, row in enumerate(existing):
        fp = row_fingerprint(row)
        existing_map[fp] = (DATA_START + i, row[:10])

    print(f"已有记录: {len(existing_map)} 条")

    new_rows = []
    update_rows = []

    for master_idx, row in enumerate(candidates):
        order = row[ORDER_COL].strip() if len(row) > ORDER_COL else ""
        ship = row[SHIP_COL].strip() if len(row) > SHIP_COL else ""
        tracker = row[TRACKER_COL].strip() if len(row) > TRACKER_COL else ""
        customer = row[CUSTOMER_COL].strip() if len(row) > CUSTOMER_COL else ""
        remark = row[REMARK_COL].strip() if len(row) > REMARK_COL else ""

        new_data = [
            order if order else f"(无工单-{master_idx+3})",  # A 维修工单
            tracker,                                          # B 跟踪人
            remark,                                           # C 维修备件及数量（备注内容）
            "",                                                # D 备件序列号
            "",                                                # E 领料时间
            "",                                                # F 是否退回
            "",                                                # G 退料时间
            "",                                                # H 退回备注
            customer,                                         # I 客户
            ship,                                             # J 船号
        ]

        if order:
            fp = ("order", order)
        else:
            fp = ("no_order", remark[:20])

        if fp in existing_map:
            # 已存在 -> 检查备注是否有变化
            old_remark = existing_map[fp][1][2].strip() if len(existing_map[fp][1]) > 2 else ""
            if old_remark != remark:
                update_rows.append((existing_map[fp][0], new_data))
        else:
            new_rows.append(new_data)

    # 追加新行
    if new_rows:
        start = DATA_START + len(existing_map)
        updated = client.write_range(FILE_ID, TARGET_SHEET, start, 0, new_rows)
        print(f"新增 {len(new_rows)} 行, {updated} 个单元格")

    # 更新已有行
    for row_num, data in update_rows:
        updated = client.write_range(FILE_ID, TARGET_SHEET, row_num, 0, [data])
        print(f"更新 Row {row_num+1}: {data[0][:30]} ({updated} cells)")

    if not new_rows and not update_rows:
        print("无变化")


if __name__ == "__main__":
    main()
