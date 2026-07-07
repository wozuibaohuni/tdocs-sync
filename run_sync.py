"""
腾讯文档 总表→物料跟踪表 自动同步脚本

业务场景：
  总表（故障跟踪表）记录全量售后工单。部分工单需要给客户寄出配件，
  客户更换配件后需将旧配件寄回。为方便领导查看配件使用与回收情况，
  将总表中"领料"列有值的工单行，提取关键信息同步到物料跟踪表。

同步规则：
  - 以工单号为主键（无工单号则以 船号|领料 标识）
  - 总表 A/B/C/I/J 五列任一变更 → 下次轮询自动更新目标表
  - D-H 列为人工填写（序列号/时间/退回等），脚本绝不写入或覆写
  - 总表领料清空 → 目标表对应行自动清除
  - 绝不修改总表，只读取
"""

import os
from lib.tdocs import TdocsClient

# ---- 环境变量 ----
FILE_ID       = os.environ["TDOCS_FILE_ID"]
MASTER_SHEET  = os.environ["TDOCS_MASTER_SHEET_ID"]
TARGET_SHEET  = os.environ["TDOCS_TARGET_SHEET_ID"]

# ---- 总表列索引（0-based，对应 A-Y）----
PICK_COL      = int(os.environ.get("TDOCS_PICK_COL",     "24"))  # 领料（筛选条件 + 数据源）
ORDER_COL     = int(os.environ.get("TDOCS_ORDER_COL",    "22"))  # 工单号（主键）
TRACKER_COL   = int(os.environ.get("TDOCS_TRACKER_COL",  "11"))  # 跟踪人
CUSTOMER_COL  = int(os.environ.get("TDOCS_CUSTOMER_COL",  "5"))  # 客户
SHIP_COL      = int(os.environ.get("TDOCS_SHIP_COL",      "4"))  # 船号

# ---- 常量 ----
DATA_START    = 4             # 目标表数据起始行（0-based，即第 5 行）
MASTER_RANGE  = "A3:Y301"    # 总表读取范围
TARGET_RANGE  = "A5:J202"    # 目标表读取范围


# ---------------------------------------------------------------------------
# 指纹
# ---------------------------------------------------------------------------

def fingerprint(order, ship, pick):
    """生成行唯一标识，匹配总表与目标表中的对应行。

    有工单号 → 用工单号；无工单号 → 用 船号|领料前20字符。
    """
    order = (order or "").strip()
    if order:
        return ("order", order)
    ship = (ship or "").strip()
    pick = (pick or "").strip()
    return ("no_order", f"{ship}|{pick[:20]}")


# ---------------------------------------------------------------------------
# 行数据提取 & 组装
# ---------------------------------------------------------------------------

def extract(row):
    """从总表行中提取 5 个同步字段。"""
    def col(i):
        return row[i].strip() if len(row) > i else ""
    return col(ORDER_COL), col(SHIP_COL), col(TRACKER_COL), col(CUSTOMER_COL), col(PICK_COL)


def build_row(order, ship, tracker, cust, pick, old_row=None):
    """组装目标表的一行（10 列）。

    old_row 传入时，D-H 列沿用旧值（人工填写内容不丢失）；
    不传入时 D-H 留空（新增行）。
    """
    if old_row and len(old_row) >= 8:
        d, e, f, g, h = old_row[3], old_row[4], old_row[5], old_row[6], old_row[7]
    else:
        d = e = f = g = h = ""

    return [
        order if order else "无工单",  # A  维修工单
        tracker,                       # B  跟踪人
        pick,                          # C  维修备件及数量
        d,                             # D  备件序列号（人工）
        e,                             # E  领料时间  （人工）
        f,                             # F  是否退回  （人工）
        g,                             # G  退料时间  （人工）
        h,                             # H  退回备注  （人工）
        cust,                          # I  客户
        ship,                          # J  船号
    ]


def synced(row):
    """取脚本负责的 5 列 (A,B,C,I,J)，用于变更比对。"""
    return (row[0], row[1], row[2], row[8], row[9])


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    client = TdocsClient(
        access_token=os.environ["TDOCS_ACCESS_TOKEN"],
        client_id=os.environ["TDOCS_CLIENT_ID"],
        open_id=os.environ["TDOCS_OPEN_ID"],
    )

    # —— 1. 读总表，筛选领料非空的行 ——
    master_rows = client.read_range(FILE_ID, MASTER_SHEET, MASTER_RANGE)
    print(f"总表读取 {len(master_rows)} 行")

    candidates = [r for r in master_rows
                  if len(r) > PICK_COL and r[PICK_COL].strip()]
    print(f"领料有值: {len(candidates)} 行")

    # —— 2. 读目标表现有数据，建索引 ——
    existing = client.read_range(FILE_ID, TARGET_SHEET, TARGET_RANGE)
    print(f"目标表已有 {len(existing)} 行")

    index = {}       # 指纹 → 行数据（10列）
    for row in existing:
        if len(row) < 10:
            continue
        o = row[0].strip() if row[0] else ""
        s = row[9].strip() if len(row) > 9 and row[9] else ""
        p = row[2].strip() if len(row) > 2 and row[2] else ""
        index[fingerprint(o, s, p)] = row[:10]

    # —— 3. 遍历候选行，合并生成完整结果 ——
    result = []
    stats = {"new": 0, "update": 0, "skip": 0}

    for row in candidates:
        order, ship, tracker, cust, pick = extract(row)
        fp = fingerprint(order, ship, pick)

        if fp in index:
            old_row = index[fp]
            new_row = build_row(order, ship, tracker, cust, pick, old_row)
            if synced(new_row) != synced(old_row):
                result.append(new_row)
                stats["update"] += 1
            else:
                result.append(old_row)
                stats["skip"] += 1
        else:
            result.append(build_row(order, ship, tracker, cust, pick))
            stats["new"] += 1

    # —— 4. 整块写入目标表 ——
    updated = client.write_range(FILE_ID, TARGET_SHEET, DATA_START, 0, result)
    print(f"写入 {len(result)} 行, {updated} 个单元格")

    # —— 5. 清除尾部残留行（总表领料清空导致目标表行数减少时） ——
    if len(result) < len(existing):
        extra = len(existing) - len(result)
        empty_rows = [[""] * 10 for _ in range(extra)]
        start = DATA_START + len(result)
        client.write_range(FILE_ID, TARGET_SHEET, start, 0, empty_rows)
        print(f"清除 {extra} 行（领料已清空）")

    # —— 6. 汇总 ——
    print(f"同步完成: 新增 {stats['new']} / 更新 {stats['update']} / "
          f"跳过 {stats['skip']} / 目标表共 {len(result)} 行")


if __name__ == "__main__":
    main()
