# -*- coding: utf-8 -*-
import re
import json
import html
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
TEL_RE = re.compile(r"tel[:=/%22%3A\-_]*0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}", re.IGNORECASE)

KEYWORDS = [
    "관리사무소",
    "관리사무실",
    "관리소",
    "대표전화",
    "관리비",
    "management",
    "office",
    "tel",
    "phone",
]

def norm_phone(p):
    nums = re.sub(r"\D", "", p)
    if len(nums) == 10:
        return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    if len(nums) == 11:
        return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return ""

def is_bad_phone(phone):
    if not phone:
        return True
    if phone.startswith("000-"):
        return True
    if phone.startswith("010-"):
        return True
    if phone in {
        "000-0000-0000",
        "010-0000-1000",
        "012-345-6789",
    }:
        return True
    return False

def collect_phones(text):
    found = set()
    for raw in PHONE_RE.findall(text or ""):
        phone = norm_phone(raw)
        if phone and not is_bad_phone(phone):
            found.add(phone)
    return sorted(found)

def collect_tel_phones(text):
    found = set()
    for raw in TEL_RE.findall(text or ""):
        phone = norm_phone(raw)
        if phone and not is_bad_phone(phone):
            found.add(phone)
    return sorted(found)

def clean_context(s):
    s = html.unescape(s or "")
    s = s.replace("\\u003C", "<").replace("\\u003E", ">")
    s = s.replace("\\\"", "\"")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_keyword_contexts(text):
    contexts = []
    if not text:
        return contexts

    decoded_text = html.unescape(text)

    for kw in KEYWORDS:
        start = 0
        while True:
            idx = decoded_text.find(kw, start)
            if idx == -1:
                break

            left = max(0, idx - 900)
            right = min(len(decoded_text), idx + 900)
            chunk = decoded_text[left:right]

            contexts.append({
                "keyword": kw,
                "index": idx,
                "phones": collect_phones(chunk),
                "tel_phones": collect_tel_phones(chunk),
                "context": clean_context(chunk)[:2500],
            })

            start = idx + len(kw)

    return contexts

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    return r.url, r.text, r.status_code

def main():
    queries = [
        f"{APT_NAME} 네이버 부동산 관리사무소",
        f"{APT_NAME} 관리사무소",
        f"{APT_NAME} 관리사무소 전화번호",
        f"{APT_NAME} {ADDRESS} 관리사무소",
    ]

    all_phones = set()
    all_tel_phones = set()
    context_phones = set()
    pages = []

    for q in queries:
        url = "https://search.naver.com/search.naver?where=nexearch&query=" + quote(q)
        print("\n검색:", q)

        final_url, raw_html, status = fetch(url)
        decoded = html.unescape(raw_html)

        phones_all = collect_phones(decoded)
        tel_phones = collect_tel_phones(decoded)
        contexts = extract_keyword_contexts(decoded)

        page_context_phones = set()
        for c in contexts:
            for p in c["phones"]:
                page_context_phones.add(p)

        all_phones.update(phones_all)
        all_tel_phones.update(tel_phones)
        context_phones.update(page_context_phones)

        print("HTTP:", status)
        print("전체 번호:", phones_all)
        print("TEL 번호:", tel_phones)
        print("키워드 주변 번호:", sorted(page_context_phones))

        # 로그 너무 길어지는 것 방지: context는 JSON에만 저장
        pages.append({
            "query": q,
            "final_url": final_url,
            "status": status,
            "all_phones": phones_all,
            "tel_phones": tel_phones,
            "keyword_context_phones": sorted(page_context_phones),
            "contains_expected_in_all": EXPECTED_PHONE in phones_all,
            "contains_expected_in_tel": EXPECTED_PHONE in tel_phones,
            "contains_expected_in_context": EXPECTED_PHONE in page_context_phones,
            "keyword_contexts": contexts[:30],
        })

    result = {
        "apt_name": APT_NAME,
        "address": ADDRESS,
        "expected_phone": EXPECTED_PHONE,
        "all_found_phones": sorted(all_phones),
        "tel_found_phones": sorted(all_tel_phones),
        "context_found_phones": sorted(context_phones),
        "success_all": EXPECTED_PHONE in all_phones,
        "success_tel": EXPECTED_PHONE in all_tel_phones,
        "success_context": EXPECTED_PHONE in context_phones,
        "pages": pages,
    }

    OUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n===== 최종 결과 =====")
    print("전체 번호 성공:", result["success_all"])
    print("TEL 번호 성공:", result["success_tel"])
    print("키워드 주변 성공:", result["success_context"])
    print("결과 저장:", OUT_PATH)

    if result["success_tel"]:
        print("\n대박: tel 링크 규칙으로 정답 찾음:", EXPECTED_PHONE)
    elif result["success_context"]:
        print("\n성공: 키워드 주변 번호로 정답 찾음:", EXPECTED_PHONE)
    else:
        print("\n실패: 아직 정답 번호를 안정적으로 못 찾음.")

if __name__ == "__main__":
    main()
