# -*- coding: utf-8 -*-
import re
import json
import requests
from pathlib import Path
from urllib.parse import quote

APT_NAME = "권선자이e편한세상"
ADDRESS = "경기 수원시 권선구 권광로 55"
EXPECTED_PHONE = "031-898-6527"

OUT_PATH = Path("naver_land_auto_search_result.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; SM-S948N) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
KEYWORDS = ["관리사무소", "관리사무실", "관리소", "대표전화"]

def norm_phone(p):
    nums = re.sub(r"\D", "", p)
    if len(nums) == 10:
        return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    if len(nums) == 11:
        return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return ""

def is_bad_phone(phone):
    bads = {
        "000-0000-0000",
        "010-0000-1000",
        "012-345-6789",
    }
    if not phone:
        return True
    if phone in bads:
        return True
    if phone.startswith("000-"):
        return True
    if phone.startswith("010-"):
        return True
    return False

def collect_all_phones(text):
    found = set()
    for raw in PHONE_RE.findall(text or ""):
        phone = norm_phone(raw)
        if phone and not is_bad_phone(phone):
            found.add(phone)
    return sorted(found)

def collect_context_phones(text):
    if not text:
        return []

    found = set()

    for kw in KEYWORDS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break

            left = max(0, idx - 500)
            right = min(len(text), idx + 500)
            chunk = text[left:right]

            for raw in PHONE_RE.findall(chunk):
                phone = norm_phone(raw)
                if phone and not is_bad_phone(phone):
                    found.add(phone)

            start = idx + len(kw)

    return sorted(found)

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    return r.url, r.text, r.status_code

def main():
    queries = [
        f"{APT_NAME} 관리사무소",
        f"{APT_NAME} 관리사무소 전화번호",
        f"{APT_NAME} {ADDRESS} 관리사무소",
        f"{APT_NAME} 네이버 부동산 관리사무소",
    ]

    all_phones = set()
    context_phones = set()
    pages = []

    for q in queries:
        url = "https://search.naver.com/search.naver?where=nexearch&query=" + quote(q)
        print("\n검색:", q)

        final_url, html, status = fetch(url)

        phones_all = collect_all_phones(html)
        phones_context = collect_context_phones(html)

        all_phones.update(phones_all)
        context_phones.update(phones_context)

        print("HTTP:", status)
        print("전체 번호:", phones_all)
        print("관리사무소 주변 번호:", phones_context)

        pages.append({
            "query": q,
            "final_url": final_url,
            "status": status,
            "all_phones": phones_all,
            "context_phones": phones_context,
            "contains_expected_in_context": EXPECTED_PHONE in phones_context,
        })

    result = {
        "apt_name": APT_NAME,
        "address": ADDRESS,
        "expected_phone": EXPECTED_PHONE,
        "all_found_phones": sorted(all_phones),
        "context_found_phones": sorted(context_phones),
        "success": EXPECTED_PHONE in context_phones,
        "pages": pages,
    }

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 최종 결과 =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["success"]:
        print("\n성공: 관리사무소 주변 번호로 정답 찾음:", EXPECTED_PHONE)
    else:
        print("\n실패: 관리사무소 주변 번호에서는 아직 정답 못 찾음.")

if __name__ == "__main__":
    main()
