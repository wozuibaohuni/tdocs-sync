"""
腾讯文档 Open API v3 封装。
只封装本项目需要的三个操作：读元数据、读范围、批量写入。
"""

import httpx

API_BASE = "https://docs.qq.com/openapi"


class TdocsClient:
    def __init__(self, access_token: str, client_id: str, open_id: str):
        self._headers = {
            "Access-Token": access_token,
            "Client-Id": client_id,
            "Open-Id": open_id,
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        kwargs.setdefault("timeout", 60)  # 腾讯文档 API 偶有延迟，默认 60s
        r = httpx.request(
            method, url, headers={**self._headers, **kwargs.pop("headers", {})}, **kwargs
        )
        r.raise_for_status()
        data = r.json()
        if "code" in data and data["code"] != 0:
            raise RuntimeError(f"API error: {data.get('message', data)}")
        return data

    # ---- 读 ----

    def get_file_meta(self, file_id: str) -> list[dict]:
        data = self._request("GET", f"/spreadsheet/v3/files/{file_id}")
        return data.get("properties", [])

    def read_range(self, file_id: str, sheet_id: str, range_: str) -> list[list[str]]:
        """
        读取指定范围，返回二维文本数组。
        支持 text / select / number / time 四种单元格类型。
        """
        data = self._request("GET", f"/spreadsheet/v3/files/{file_id}/{sheet_id}/{range_}")
        rows = data.get("gridData", {}).get("rows", [])
        result = []
        for row in rows:
            cells = [_extract_cell_text(v) for v in row.get("values", [])]
            result.append(cells)
        return result

    # ---- 写 ----

    def write_range(
        self,
        file_id: str,
        sheet_id: str,
        start_row: int,
        start_col: int,
        rows: list[list[str]],
    ) -> int:
        grid_rows = []
        for row_data in rows:
            values = [{"cellValue": {"text": text}} for text in row_data]
            grid_rows.append({"values": values})

        body = {
            "requests": [
                {
                    "updateRangeRequest": {
                        "sheetId": sheet_id,
                        "gridData": {
                            "startRow": start_row,
                            "startColumn": start_col,
                            "rows": grid_rows,
                        },
                    }
                }
            ]
        }

        data = self._request(
            "POST",
            f"/spreadsheet/v3/files/{file_id}/batchUpdate",
            json=body,
        )
        resp = data.get("responses", [{}])[0]
        return resp.get("updateRangeResponse", {}).get("updatedCells", 0)


# ---- 单元格值提取（text / select / number / time）----

def _extract_cell_text(v) -> str:
    """从 API 返回的单元格对象中提取可读文本。"""
    if not v or not v.get("cellValue"):
        return ""
    cv = v["cellValue"]

    if "text" in cv:
        return cv["text"] or ""

    if "select" in cv:
        sel = cv["select"]
        selected = set(sel.get("value", []))
        texts = [o["text"] for o in sel.get("options", []) if o["id"] in selected]
        return ", ".join(texts)

    if "number" in cv:
        return str(cv["number"])

    if "time" in cv:
        t = cv["time"]
        return f"{t.get('year','')}-{t.get('month',''):0>2d}-{t.get('day',''):0>2d}"

    return ""
