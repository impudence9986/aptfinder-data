# -*- coding: utf-8 -*-
import json
import os
import time
import requests
from pathlib import Path

DATA_DIR = Path("data")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

SLEEP_SEC = 0.12
DRY_RUN = False


def kakao_address_search(address):
    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"
    }
    params = {
        "query": address
    }

    try:
        r = requests.get(
            KAKAO_ADDRESS_URL,
            headers=headers,
            params=params,
            timeout=10
        )

        if r.status_code != 200:
            print(f"  [카카오 실패] {r.status_code} / {address}")
            print(f"  응답: {r.text[:300]}")
            return None

        data = r.json()
        docs = data.get("documents", [])

        if not docs:
            return None

        return docs[0]

    except Exception as e:
        print(f"  [예외] {address} / {e}")
        return None


def extract_road_jibun(doc):
    road = ""
    jibun = ""

    road_obj = doc.get("road_address")
    addr_obj = doc.get("address")

    if road_obj:
        road = road_obj.get("address_name", "") or ""

    if addr_obj:
        jibun = addr_obj.get("address_name", "") or ""

    return road.strip(), jibun.strip()


def normalize_for_compare(value):
    return (
        (value or "")
        .replace(" ", "")
        .replace("\n", "")
        .strip()
    )


def normalize_display_address(road, jibun):
    road = (road or "").strip()
    jibun = (jibun or "").strip()

    if road and jibun and normalize_for_compare(road) != normalize_for_compare(jibun):
        return f"{road}\n{jibun}"

    if road:
        return road

    if jibun:
        return jibun

    return ""


def needs_jibun_fill(item):
    road = (item.get("roadAddress") or "").strip()
    jibun = (item.get("jibunAddress") or "").strip()

    if not road:
        return False

    if jibun:
        return False

    return True


def process_file(path):
    print(f"\n처리 시작: {path}")

    with path.open("r", encoding="utf-8") as f:
        db = json.load(f)

    items = db.get("items", [])

    changed = 0
    target_count = 0
    failed_count = 0

    for idx, item in enumerate(items, start=1):
        if not needs_jibun_fill(item):
            continue

        target_count += 1

        name = item.get("name", "")
        old_road = (item.get("roadAddress") or "").strip()

        print(f"  [{idx}/{len(items)}] 지번 보강: {name} / {old_road}")

        doc = kakao_address_search(old_road)
        time.sleep(SLEEP_SEC)

        if not doc:
            failed_count += 1
            print("    → 실패: 결과 없음")
            continue

        new_road, new_jibun = extract_road_jibun(doc)

        if not new_jibun:
            failed_count += 1
            print("    → 실패: 지번 없음")
            continue

        if new_road:
            item["roadAddress"] = new_road

        item["jibunAddress"] = new_jibun
        item["address"] = normalize_display_address(
            item.get("roadAddress", ""),
            item.get("jibunAddress", "")
        )
        item["addressQuality"] = "ROAD_AND_JIBUN"

        changed += 1

        print(f"    → 완료: {new_jibun}")

    if changed > 0 and not DRY_RUN:
        with path.open("w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"완료: 대상 {target_count}개 / 보강 {changed}개 / 실패 {failed_count}개")

    return target_count, changed, failed_count


def main():
    if not KAKAO_REST_API_KEY:
        print("KAKAO_REST_API_KEY가 없습니다.")
        print("GitHub Actions Secrets에 KAKAO_REST_API_KEY가 있는지 확인하세요.")
        return

    if not DATA_DIR.exists():
        print("data 폴더가 없습니다.")
        return

    files = sorted(DATA_DIR.glob("*.json"))

    files = [
        f for f in files
        if not f.name.startswith("_")
    ]

    if not files:
        print("data/*.json 파일이 없습니다.")
        return

    total_target = 0
    total_changed = 0
    total_failed = 0

    print("지번 보강 시작")
    print(f"대상 파일 수: {len(files)}")

    for path in files:
        target, changed, failed = process_file(path)
        total_target += target
        total_changed += changed
        total_failed += failed

    print("\n전체 완료")
    print(f"전체 대상: {total_target}개")
    print(f"전체 보강: {total_changed}개")
    print(f"전체 실패: {total_failed}개")


if __name__ == "__main__":
    main()
