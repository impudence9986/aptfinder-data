# -*- coding: utf-8 -*-
import re
import json
import requests
from pathlib import Path
from urllib.parse import unquote

SHARE_URL = "https://naver.me/5eUmYYGC"
EXPECTED_PHONE = "031-898-6527"

OUT_PATH = Path("naver_land_test_result.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://new.land.naver.com/",
}

PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
COMPLEX_RE_LIST = [
    re.compile(r"/complexes/(\d+)"),
    re.compile(r"complexNo[=:\"']+(\d+)"),
    re.compile(r"complexNo%22%3A(\d+)"),
    re.compile(r"complexes%2F(\d+)"),
]


def norm_phone(p: str) -> str:
    nums = re.sub(r"\D", "", p)
    if len(nums) == 10:
        return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    if len(nums) == 11:
        return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return p


def collect_phones(text: str) -> list[str]:
    if not text:
        return []
    return sorted({norm_phone(x) for x in PHONE_RE.findall(text)})


def find_complex_nos(text: str) -> list[str]:
    if not text:
        return []

    targets = {text, unquote(text)}

    found = set()
    for t in targets:
        for rx in COMPLEX_RE_LIST:
            for m in rx.findall(t):
                found.add(str(m))

    return sorted(found)


def get_text(url: str) -> tuple[str, str, int]:
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    return r.url, r.text, r.status_code


def try_api(complex_no: str) -> dict:
    urls = [
        f"https://new.land.naver.com/api/complexes/{complex_no}",
        f"https://new.land.naver.com/api/complexes/overview/{complex_no}",
        f"https://new.land.naver.com/api/complexes/{complex_no}?sameAddressGroup=false",
    ]

    api_results = []

    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            text = r.text
            phones = collect_phones(text)

            api_results.append({
                "url": url,
                "status_code": r.status_code,
                "phones": phones,
                "contains_expected": EXPECTED_PHONE in phones,
                "sample": text[:1000],
            })
        except Exception as e:
            api_results.append({
                "url": url,
                "error": str(e),
            })

    return {
        "complex_no": complex_no,
        "api_results": api_results,
    }


def main():
    result = {
        "share_url": SHARE_URL,
        "expected_phone": EXPECTED_PHONE,
        "final_url": None,
        "status_code": None,
        "phones_from_share_page": [],
        "complex_nos": [],
        "api_checks": [],
        "success": False,
    }

    print("단축링크 접속:", SHARE_URL)

    final_url, html, status = get_text(SHARE_URL)

    print("최종 URL:", final_url)
    print("HTTP:", status)

    result["final_url"] = final_url
    result["status_code"] = status

    phones = collect_phones(html + "\n" + final_url)
    complex_nos = find_complex_nos(html + "\n" + final_url)

    result["phones_from_share_page"] = phones
    result["complex_nos"] = complex_nos

    print("공유페이지에서 찾은 번호:", phones)
    print("찾은 complexNo:", complex_nos)

    for no in complex_nos:
        print(f"\nAPI 테스트 complexNo={no}")
        check = try_api(no)
        result["api_checks"].append(check)

        for api in check["api_results"]:
            print("URL:", api.get("url"))
            print("STATUS:", api.get("status_code"))
            print("PHONES:", api.get("phones"))

            if api.get("contains_expected"):
                result["success"] = True

    if EXPECTED_PHONE in phones:
        result["success"] = True

    OUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n===== 최종 결과 =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["success"]:
        print("\n성공: 관리사무소 번호 수집됨:", EXPECTED_PHONE)
    else:
        print("\n실패: 아직 관리사무소 번호를 못 찾음.")
        print("그래도 result JSON에 최종 URL/API 응답 샘플 저장됨.")

    # 테스트 실패여도 workflow 자체는 실패시키지 않음
    # 그래야 artifact를 받을 수 있음.


if __name__ == "__main__":
    main()
