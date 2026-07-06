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
        r = httpx.request(
            method, url, headers={**self._headers, **kwargs.pop("headers", {})}, **kwargs
        )
        r.raise_for_status()
        data = r.json()
        # 腾讯文档 API 报错时 HTTP 200 + code 字段
        if "code" in data and data["code"] != 0:
            raise RuntimeError(f"API error: {data.get('message', data)}")
        return data

    # ---- 读 ----

    def get_file_meta(self, file_id: str) -> list[dict]:
        """获取表格所有 sheet 的元数据."""
        data = self._request("GET", f"/spreadsheet/v3/files/{file_id}")
        return data.get("properties", [])

    def read_range(self, file_id: str, sheet_id: str, range_: str) -> list[list[str]]:
        """
        读取指定范围，返回二维文本数组。
        range_ 示例: "A1:X300"
        """
        data = self._request("GET", f"/spreadsheet/v3/files/{file_id}/{sheet_id}/{range_}")
        rows = data.get("gridData", {}).get("rows", [])
        result = []
        for row in rows:
            cells = []
            for v in row.get("values", []):
                if v and v.get("cellValue"):
                    cells.append(v["cellValue"].get("text", ""))
                else:
                    cells.append("")
            result.append(cells)
        return result

    # ---- 写 ----

    def write_range(
        self,
        file_id: str,
        sheet_id: str,
        start_row: int,      # 0-based
        start_col: int,       # 0-based
        rows: list[list[str]],
    ) -> int:
        """
        将 rows（二维文本数组）写入指定位置。
        返回更新的单元格数量。
        """
        grid_rows = []
        for row_data in rows:
            values = []
            for text in row_data:
                values.append({"cellValue": {"text": text}})
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
