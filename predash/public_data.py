"""Public-institution data used by the PreDash home dashboard."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import requests


class PublicDataError(RuntimeError):
    pass


def _get_json(url, params=None):
    try:
        response = requests.get(url, params=params, timeout=(8, 20))
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PublicDataError("공공기관 API 응답을 확인하지 못했습니다.") from exc


def ecos_key_indicators():
    """Return selected live values from Bank of Korea ECOS KeyStatisticList."""
    key = os.getenv("ECOS_API_KEY", "").strip()
    if not key:
        raise PublicDataError("ECOS_API_KEY가 설정되지 않았습니다.")
    url = f"https://ecos.bok.or.kr/api/KeyStatisticList/{key}/json/kr/1/100"
    payload = _get_json(url)
    block = payload.get("KeyStatisticList", {})
    if "row" not in block:
        message = (block.get("RESULT") or payload.get("RESULT") or {}).get("MESSAGE")
        raise PublicDataError(message or "ECOS 주요지표 응답에 데이터가 없습니다.")
    rows = block["row"]

    # Prefer familiar macro indicators; names can vary slightly when ECOS revises labels.
    wanted = [
        ("기준금리", ("한국은행 기준금리", "기준금리")),
        ("원/달러 환율", ("원/달러", "원달러", "환율")),
        ("소비자물가", ("소비자물가",)),
        ("GDP 성장률", ("경제성장률", "GDP")),
    ]
    selected = []
    used = set()
    for label, needles in wanted:
        hit = next((r for r in rows if any(n.lower() in str(r.get("KEYSTAT_NAME", "")).lower() for n in needles)
                    and str(r.get("KEYSTAT_NAME", "")) not in used), None)
        if hit:
            used.add(str(hit.get("KEYSTAT_NAME", "")))
            selected.append({
                "label": label,
                "name": hit.get("KEYSTAT_NAME", label),
                "value": hit.get("DATA_VALUE", "-"),
                "unit": hit.get("UNIT_NAME", ""),
                "cycle": hit.get("CYCLE", ""),
            })
    if not selected:
        raise PublicDataError("ECOS 주요지표에서 표시할 항목을 찾지 못했습니다.")
    return {
        "source": "한국은행 ECOS",
        "items": selected,
        "fetched": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M"),
    }


def kosis_connection():
    """Validate the KOSIS key against the official statistics-list endpoint."""
    key = os.getenv("KOSIS_API_KEY", "").strip()
    if not key:
        return {"ok": False, "message": "키 없음"}
    payload = _get_json(
        "https://kosis.kr/openapi/statisticsList.do",
        {"method": "getList", "apiKey": key, "vwCd": "MT_ZTITLE",
         "parentId": "", "format": "json", "jsonVD": "Y"},
    )
    if isinstance(payload, list):
        return {"ok": True, "message": "API 응답 정상"}
    if isinstance(payload, dict) and payload.get("err"):
        return {"ok": False, "message": str(payload.get("err"))}
    return {"ok": bool(payload), "message": "API 응답 확인" if payload else "응답 없음"}


def configured_sources():
    aliases = {
        "OpenDART": ("DART_CRTFC_KEY",),
        "공공데이터포털": ("DATA_GO_KR_SERVICE_KEY",),
        "KRX": ("KRX_AUTH_KEY",),
        "관세청": ("CUSTOMS_API_KEY",),
        "한국은행 ECOS": ("ECOS_API_KEY",),
        "KOSIS": ("KOSIS_API_KEY",),
    }
    return {name: any(os.getenv(k, "").strip() for k in keys) for name, keys in aliases.items()}
