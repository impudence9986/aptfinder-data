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

def norm_phone(p):
    nums = re.sub(r"\D", "", p)
    if len(nums) == 10:
        return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    if len(nums) == 11:
        return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return p

def collect_phones(text):
    return sorted({norm_phone(x) for x in PHONE_RE.findall(text or "")})

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    return r.url, r.text, r.status_code

def main():
    queries = [
        f"{APT_NAME} 관리사무소",
        f"{APT_NAME} {ADDRESS}",
        f"{APT_NAME} 네이버 부동산",
        f"{ADDRESS} 네이버 부동산",
    ]

    all_phones = set()
    pages = []

    for q in queries:
        url = "https://search.naver.com/search.naver?where=nexearch&query=" + quote(q)
        print("\n검색:", q)
        print("URL:", url)

        final_url, html, status = fetch(url)
        phones = collect_phones(html)

        print("HTTP:", status)
        print("찾은 번호:", phones)

        all_phones.update(phones)

        pages.append({
            "query": q,
            "url": url,
            "final_url": final_url,
            "status": status,
            "phones": phones,
            "contains_expected": EXPECTED_PHONE in phones,
            "html_sample": html[:1500],
        })

    result = {
        "apt_name": APT_NAME,
        "address": ADDRESS,
        "expected_phone": EXPECTED_PHONE,
        "found_phones": sorted(all_phones),
        "success": EXPECTED_PHONE in all_phones,
        "pages": pages,
    }

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 최종 결과 =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["success"]:
        print("\n성공: 자동검색만으로 번호 찾음:", EXPECTED_PHONE)
    else:
        print("\n실패: 자동검색 결과 HTML에서는 아직 번호 못 찾음.")

if __name__ == "__main__":
    main()
