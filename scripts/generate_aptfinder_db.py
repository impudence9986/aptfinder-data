# -*- coding: utf-8 -*-
"""
AptFinder 전국/지역별 DB 생성기 - 시도/시군구 엄격 분리 버전

실행 전:
1) config.json에 카카오/네이버/K-apt 키 입력
2) 터미널에서:
   pip install -r requirements.txt
   python generate_aptfinder_db.py --region "경기도|성남시"

전체 실행:
   python generate_aptfinder_db.py --all

결과:
output/
 ├ metadata.json
 └ data/
    ├ gyeonggi_seongnam.json
    └ ...
"""

import argparse
import os
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


CONFIG_PATH = Path("config.json")
OUTPUT_DIR = Path("output")
DATA_DIR = OUTPUT_DIR / "data"
STATE_PATH = OUTPUT_DIR / "update_state.json"

KAPT_LIST_URL = "https://apis.data.go.kr/1613000/AptListService3/getTotalAptList3"
KAPT_DETAIL_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
NAVER_LOCAL_URL = "https://openapi.naver.com/v1/search/local.json"
NAVER_WEB_URL = "https://openapi.naver.com/v1/search/webkr.json"
NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
NAVER_CAFE_URL = "https://openapi.naver.com/v1/search/cafearticle.json"

PHONE_RE = re.compile(r"(0\d{1,2})[-\s)]?(\d{3,4})[-\s]?(\d{4})")

# 1차는 전국 핵심 시군구. 필요하면 계속 추가 가능.
REGION_MAP: Dict[str, List[str]] = {
    "서울특별시": [
        "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구",
        "노원구","도봉구","동대문구","동작구","마포구","서대문구","서초구","성동구",
        "성북구","송파구","양천구","영등포구","용산구","은평구","종로구","중구","중랑구"
    ],
    "부산광역시": [
        "강서구","금정구","기장군","남구","동구","동래구","부산진구","북구","사상구",
        "사하구","서구","수영구","연제구","영도구","중구","해운대구"
    ],
    "대구광역시": ["군위군","남구","달서구","달성군","동구","북구","서구","수성구","중구"],
    "인천광역시": ["강화군","계양구","남동구","동구","미추홀구","부평구","서구","연수구","옹진군","중구"],
    "광주광역시": ["광산구","남구","동구","북구","서구"],
    "대전광역시": ["대덕구","동구","서구","유성구","중구"],
    "울산광역시": ["남구","동구","북구","울주군","중구"],
    "세종특별자치시": ["세종시"],
    "경기도": [
        "가평군","고양시","과천시","광명시","광주시","구리시","군포시","김포시",
        "남양주시","동두천시","부천시","성남시","수원시","시흥시","안산시","안성시",
        "안양시","양주시","양평군","여주시","연천군","오산시","용인시","의왕시",
        "의정부시","이천시","파주시","평택시","포천시","하남시","화성시"
    ],
    "강원특별자치도": [
        "강릉시","고성군","동해시","삼척시","속초시","양구군","양양군","영월군",
        "원주시","인제군","정선군","철원군","춘천시","태백시","평창군","홍천군",
        "화천군","횡성군"
    ],
    "충청북도": ["괴산군","단양군","보은군","영동군","옥천군","음성군","제천시","증평군","진천군","청주시","충주시"],
    "충청남도": [
        "계룡시","공주시","금산군","논산시","당진시","보령시","부여군","서산시",
        "서천군","아산시","예산군","천안시","청양군","태안군","홍성군"
    ],
    "전북특별자치도": [
        "고창군","군산시","김제시","남원시","무주군","부안군","순창군","완주군",
        "익산시","임실군","장수군","전주시","정읍시","진안군"
    ],
    "전라남도": [
        "강진군","고흥군","곡성군","광양시","구례군","나주시","담양군","목포시",
        "무안군","보성군","순천시","신안군","여수시","영광군","영암군","완도군",
        "장성군","장흥군","진도군","함평군","해남군","화순군"
    ],
    "경상북도": [
        "경산시","경주시","고령군","구미시","김천시","문경시","봉화군","상주시",
        "성주군","안동시","영덕군","영양군","영주시","영천시","예천군","울릉군",
        "울진군","의성군","청도군","청송군","칠곡군","포항시"
    ],
    "경상남도": [
        "거제시","거창군","고성군","김해시","남해군","밀양시","사천시","산청군",
        "양산시","의령군","진주시","창녕군","창원시","통영시","하동군","함안군",
        "함양군","합천군"
    ],
    "제주특별자치도": ["서귀포시","제주시"],
}


# GitHub Actions 자동 업데이트용 권역 로테이션
# 월~일 순서. 호출량 보호를 위해 하루에 일부 권역만 갱신.
REGION_GROUPS: Dict[int, List[str]] = {
    0: ["서울특별시", "인천광역시", "경기도"],
    1: ["부산광역시", "울산광역시", "경상남도"],
    2: ["대구광역시", "경상북도"],
    3: ["광주광역시", "전라남도", "전북특별자치도"],
    4: ["대전광역시", "세종특별자치시", "충청남도", "충청북도"],
    5: ["강원특별자치도", "제주특별자치도"],
    6: ["MISSING_RETRY"],
}


@dataclass
class ComplexItem:
    kaptCode: str = ""
    name: str = ""
    type: str = "아파트"
    city: str = ""
    district: str = ""
    dong: str = ""
    address: str = ""
    phone: str = ""
    households: str = ""
    source: str = ""
    verifiedAt: str = ""
    detailUpdatedAt: int = 0
    listUpdatedAt: int = 0
    phoneStatus: str = "UNKNOWN"
    reportCount: int = 0
    confidenceScore: int = 0
    lastReportedAt: int = 0


def load_config() -> dict:
    """
    PC 로컬에서는 config.json 사용.
    GitHub Actions에서는 Repository Secrets 환경변수 사용.
    """
    env_config = {
        "kakao_rest_key": os.getenv("KAKAO_REST_API_KEY", "").strip(),
        "naver_client_id": os.getenv("NAVER_CLIENT_ID", "").strip(),
        "naver_client_secret": os.getenv("NAVER_CLIENT_SECRET", "").strip(),
        "kapt_service_key": os.getenv("PUBLIC_DATA_SERVICE_KEY", "").strip(),
    }

    if all(env_config.values()):
        return env_config

    if not CONFIG_PATH.exists():
        raise SystemExit(
            "config.json이 없고 환경변수도 없습니다. "
            "로컬에서는 config.json을 만들고, GitHub Actions에서는 Secrets를 등록하세요."
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def clean_html(text: str) -> str:
    return (
        text.replace("<b>", "")
        .replace("</b>", "")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def normalize_phone(value: str) -> str:
    m = PHONE_RE.search(value or "")
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def region_slug(sido: str, sigungu: str) -> str:
    roman_sido = {
        "서울특별시": "seoul", "부산광역시": "busan", "대구광역시": "daegu",
        "인천광역시": "incheon", "광주광역시": "gwangju", "대전광역시": "daejeon",
        "울산광역시": "ulsan", "세종특별자치시": "sejong", "경기도": "gyeonggi",
        "강원특별자치도": "gangwon", "충청북도": "chungbuk", "충청남도": "chungnam",
        "전북특별자치도": "jeonbuk", "전라남도": "jeonnam", "경상북도": "gyeongbuk",
        "경상남도": "gyeongnam", "제주특별자치도": "jeju",
    }.get(sido, sido)
    return f"{roman_sido}_{sigungu}".replace(" ", "_").replace("/", "_")


def parse_region_arg(arg: str) -> Tuple[str, str]:
    if "|" not in arg:
        raise SystemExit('지역 형식은 "경기도|성남시" 처럼 입력하세요.')
    sido, sigungu = arg.split("|", 1)
    return sido.strip(), sigungu.strip()



class QuotaStop(Exception):
    """API 호출량 보호를 위해 정상 중단할 때 사용"""
    pass


class ApiCallLimiter:
    def __init__(self, max_kakao: int = 7000, max_naver: int = 20000, max_kapt: int = 50000):
        self.max_kakao = max_kakao
        self.max_naver = max_naver
        self.max_kapt = max_kapt
        self.kakao_used = 0
        self.naver_used = 0
        self.kapt_used = 0

    def check_kakao(self):
        if self.kakao_used >= self.max_kakao:
            raise QuotaStop(f"카카오 호출량 보호 중단: {self.kakao_used}/{self.max_kakao}")
        self.kakao_used += 1

    def check_naver(self):
        if self.naver_used >= self.max_naver:
            raise QuotaStop(f"네이버 호출량 보호 중단: {self.naver_used}/{self.max_naver}")
        self.naver_used += 1

    def check_kapt(self):
        if self.kapt_used >= self.max_kapt:
            raise QuotaStop(f"K-apt 호출량 보호 중단: {self.kapt_used}/{self.max_kapt}")
        self.kapt_used += 1

    def snapshot(self) -> dict:
        return {
            "kakaoUsed": self.kakao_used,
            "kakaoMax": self.max_kakao,
            "naverUsed": self.naver_used,
            "naverMax": self.max_naver,
            "kaptUsed": self.kapt_used,
            "kaptMax": self.max_kapt,
        }


class AptFinderGenerator:
    def __init__(self, config: dict, limiter: Optional[ApiCallLimiter] = None):
        self.config = config
        self.session = requests.Session()
        self.kakao_headers = {"Authorization": f"KakaoAK {config['kakao_rest_key']}"}
        self.naver_headers = {
            "X-Naver-Client-Id": config["naver_client_id"],
            "X-Naver-Client-Secret": config["naver_client_secret"],
        }
        self.kapt_key = config["kapt_service_key"]
        self.limiter = limiter or ApiCallLimiter()

    def region_output_path(self, sido: str, sigungu: str) -> Path:
        slug = region_slug(sido, sigungu)
        return DATA_DIR / f"{slug}.json"

    def region_file_count(self, path: Path) -> int:
        if not path.exists():
            return -1

        try:
            with path.open("r", encoding="utf-8") as f:
                root = json.load(f)

            items = root.get("items")
            if isinstance(items, list):
                return len(items)

            return int(root.get("count") or 0)

        except Exception:
            return -1

    def should_skip_region(
        self,
        sido: str,
        sigungu: str,
        force: bool,
        min_count: int
    ) -> bool:
        if force:
            return False

        path = self.region_output_path(sido, sigungu)
        count = self.region_file_count(path)

        return count >= min_count

    def rebuild_metadata_from_output(self):
        metadata_files = []

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        for path in sorted(DATA_DIR.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    root = json.load(f)

                sido = root.get("sido", "")
                sigungu = root.get("sigungu", "")
                items = root.get("items", [])
                count = len(items) if isinstance(items, list) else int(root.get("count") or 0)

                if not sido or not sigungu:
                    continue

                metadata_files.append({
                    "sido": sido,
                    "sigungu": sigungu,
                    "file": f"data/{path.name}",
                    "version": int(root.get("version") or time.time()),
                    "updatedAt": root.get("updatedAt") or now_text(),
                    "count": count,
                })

            except Exception as e:
                print(f"metadata 스캔 실패: {path.name} / {e}")

        metadata = {
            "version": int(time.time()),
            "updatedAt": now_text(),
            "files": metadata_files,
        }

        OUTPUT_DIR.mkdir(exist_ok=True)
        with (OUTPUT_DIR / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"metadata 재작성 완료: {len(metadata_files)}개 지역")

    def audit_output(self, regions: List[Tuple[str, str]], min_count: int = 1):
        missing = []
        weak = []

        for sido, sigungu in regions:
            path = self.region_output_path(sido, sigungu)
            count = self.region_file_count(path)

            if count < 0:
                missing.append((sido, sigungu, count))
            elif count < min_count:
                weak.append((sido, sigungu, count))

        print("\n===== DB 점검 결과 =====")
        print(f"전체 대상 지역: {len(regions)}")
        print(f"파일 없음/깨짐: {len(missing)}")
        print(f"기준 미달({min_count}개 미만): {len(weak)}")

        if missing:
            print("\n[파일 없음/깨짐]")
            for sido, sigungu, _ in missing:
                print(f"  {sido}|{sigungu}")

        if weak:
            print(f"\n[기준 미달]")
            for sido, sigungu, count in weak:
                print(f"  {sido}|{sigungu} count={count}")

        if not missing and not weak:
            print("누락 의심 지역 없음")


    def load_state(self) -> dict:
        if not STATE_PATH.exists():
            return {}
        try:
            with STATE_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_state(
        self,
        group_key: str,
        completed: List[str],
        remaining: List[Tuple[str, str]],
        status: str,
        reason: str = ""
    ):
        OUTPUT_DIR.mkdir(exist_ok=True)
        state = {
            "group": group_key,
            "updatedAt": now_text(),
            "status": status,
            "reason": reason,
            "completed": completed,
            "remaining": [f"{sido}|{sigungu}" for sido, sigungu in remaining],
            "limits": self.limiter.snapshot(),
        }
        with STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def clear_state_if_done(self):
        if STATE_PATH.exists():
            try:
                STATE_PATH.unlink()
            except Exception:
                pass

    def run_regions(
        self,
        regions: List[Tuple[str, str]],
        skip_web_phone: bool = False,
        force: bool = False,
        min_count: int = 1,
        resume: bool = False,
        group_key: str = ""
    ):
        OUTPUT_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        group_key = group_key or "manual"
        completed = []

        if resume:
            state = self.load_state()
            if state.get("group") == group_key and state.get("remaining"):
                parsed_remaining = []
                for raw in state.get("remaining", []):
                    if "|" in raw:
                        parsed_remaining.append(parse_region_arg(raw))
                if parsed_remaining:
                    print(f"이전 중단 지점부터 이어서 실행: {len(parsed_remaining)}개 남음")
                    regions = parsed_remaining
                    completed = list(state.get("completed", []))

        processed = 0
        skipped = 0
        failed = 0

        try:
            for idx, (sido, sigungu) in enumerate(regions, start=1):
                path = self.region_output_path(sido, sigungu)
                current_key = f"{sido}|{sigungu}"
                remaining_after_current = regions[idx:]

                # resume/자동 업데이트에서는 force=True가 기본 권장.
                # 단, 수동으로 force=False를 쓰면 기존 정상 파일은 스킵 가능.
                if self.should_skip_region(sido, sigungu, force=force, min_count=min_count):
                    count = self.region_file_count(path)
                    skipped += 1
                    completed.append(current_key)
                    self.save_state(group_key, completed, remaining_after_current, "running")
                    print(f"\n[{idx}/{len(regions)}] {sido} {sigungu} 건너뜀 · 기존 {count}개")
                    continue

                print(f"\n[{idx}/{len(regions)}] {sido} {sigungu} 생성 시작")

                try:
                    items = self.build_region(sido, sigungu, skip_web_phone=skip_web_phone)
                    file_path = self.write_region_file(sido, sigungu, items)
                    processed += 1
                    completed.append(current_key)
                    self.save_state(group_key, completed, remaining_after_current, "running")
                    print(f"완료: {sido} {sigungu} {len(items)}개 → {file_path}")

                except QuotaStop:
                    raise

                except Exception as e:
                    failed += 1
                    print(f"실패: {sido} {sigungu} / {e}")
                    # 실패 지역은 remaining에 다시 넣어서 다음 실행 때 재시도
                    self.save_state(
                        group_key,
                        completed,
                        [(sido, sigungu)] + remaining_after_current,
                        "stopped",
                        reason=f"지역 처리 실패: {sido}|{sigungu} / {e}"
                    )

            self.rebuild_metadata_from_output()
            self.clear_state_if_done()

            print("\n전체 완료")
            print(f"처리: {processed}개 / 건너뜀: {skipped}개 / 실패: {failed}개")
            print(f"GitHub 업로드 대상 폴더: {OUTPUT_DIR.resolve()}")

        except QuotaStop as e:
            current_index = processed + skipped + failed
            remaining = regions[current_index:]
            self.save_state(group_key, completed, remaining, "stopped", reason=str(e))
            self.rebuild_metadata_from_output()
            print(f"\n호출량 보호로 정상 중단: {e}")
            print(f"다음 실행 때 --resume 옵션으로 이어서 처리됩니다.")
            print(f"남은 지역: {len(remaining)}개")


    def build_region(self, sido: str, sigungu: str, skip_web_phone: bool = False) -> List[ComplexItem]:
        apt_items = self.fetch_kapt_region(sido, sigungu)
        officetel_items = self.collect_officetels(sido, sigungu)

        merged = self.merge_items(apt_items + officetel_items)

        print(f"전화번호 보강 시작: {len(merged)}개")
        enriched = []
        for i, item in enumerate(merged, start=1):
            if not item.phone:
                item = self.enrich_phone(item, skip_web_phone=skip_web_phone)
            enriched.append(item)
            if i % 20 == 0 or i == len(merged):
                print(f"  보강 {i}/{len(merged)}")

        return self.merge_items(enriched)

    def fetch_kapt_region(self, sido: str, sigungu: str) -> List[ComplexItem]:
        print("K-apt 아파트 수집 중...")
        results = []
        page = 1
        num = 9999
        total = 10**9
        now = int(time.time() * 1000)

        while (page - 1) * num < total:
            params = {
                "serviceKey": self.kapt_key,
                "pageNo": page,
                "numOfRows": num,
                "_type": "json",
            }

            try:
                self.limiter.check_kapt()
                r = self.session.get(KAPT_LIST_URL, params=params, timeout=60)
                r.raise_for_status()
                root = r.json()

                body = root.get("response", {}).get("body", {})
                total = int(body.get("totalCount") or 0)

                items_raw = body.get("items", [])

                if isinstance(items_raw, dict):
                    items_any = items_raw.get("item", [])
                elif isinstance(items_raw, list):
                    items_any = items_raw
                else:
                    items_any = []

                if isinstance(items_any, dict):
                    items_any = [items_any]

                if not isinstance(items_any, list) or not items_any:
                    break

                for obj in items_any:
                    if not isinstance(obj, dict):
                        continue

                    address = " ".join(
                        str(obj.get(k, "")).strip()
                        for k in ["as1", "as2", "as3", "as4"]
                        if str(obj.get(k, "")).strip()
                    )

                    if not self.is_target_address(address, sido, sigungu):
                        continue

                    name = obj.get("kaptName") or obj.get("kaptNm") or ""
                    kapt_code = obj.get("kaptCode") or ""

                    if not name:
                        continue

                    detail = self.fetch_kapt_detail(kapt_code, obj, now, sido, sigungu)
                    results.append(detail)

                print(f"  K-apt page {page} 누적 {len(results)}")
                page += 1
                time.sleep(0.2)

            except Exception as e:
                print(f"  K-apt 수집 실패 page={page}: {e}")
                break

        print(f"K-apt 결과: {len(results)}개")
        return self.merge_items(results)

    def fetch_kapt_detail(self, kapt_code: str, fallback: dict, now: int, sido: str, sigungu: str) -> ComplexItem:
        if not kapt_code:
            return self.item_from_kapt_list(fallback, now, sido, sigungu)

        try:
            params = {
                "serviceKey": self.kapt_key,
                "kaptCode": kapt_code,
                "_type": "json",
            }
            self.limiter.check_kapt()
            r = self.session.get(KAPT_DETAIL_URL, params=params, timeout=40)
            r.raise_for_status()
            root = r.json()
            body = root.get("response", {}).get("body", {})
            item = body.get("item") or body.get("items", {}).get("item") or {}
            if not isinstance(item, dict):
                return self.item_from_kapt_list(fallback, now, sido, sigungu)

            name = item.get("kaptName") or item.get("kaptNm") or fallback.get("kaptName") or fallback.get("kaptNm") or ""
            address = item.get("doroJuso") or item.get("kaptAddr") or self.address_from_list(fallback)
            phone = normalize_phone(item.get("kaptTel") or item.get("kaptTelNo") or "")
            households = str(item.get("kaptdaCnt") or item.get("hoCnt") or "").split(".")[0]

            return ComplexItem(
                kaptCode=kapt_code,
                name=name,
                type=self.infer_type(item.get("codeAptNm", "")),
                city=sigungu,
                district=self.extract_district(address),
                dong=self.extract_dong(address),
                address=address,
                phone=phone,
                households=households if households.isdigit() else "",
                source="공공데이터 K-apt",
                verifiedAt="자동업데이트",
                detailUpdatedAt=now,
                listUpdatedAt=now,
                phoneStatus="CONFIRMED" if phone else "UNKNOWN",
                confidenceScore=100 if phone else 0,
            )
        except Exception:
            return self.item_from_kapt_list(fallback, now, sido, sigungu)

    def item_from_kapt_list(self, obj: dict, now: int, sido: str, sigungu: str) -> ComplexItem:
        address = self.address_from_list(obj)
        return ComplexItem(
            kaptCode=obj.get("kaptCode") or "",
            name=obj.get("kaptName") or obj.get("kaptNm") or "",
            type="아파트",
            city=sigungu,
            district=self.extract_district(address),
            dong=self.extract_dong(address),
            address=address,
            source="공공데이터 K-apt",
            verifiedAt="목록정보",
            listUpdatedAt=now,
        )

    def collect_officetels(self, sido: str, sigungu: str) -> List[ComplexItem]:
        print("오피스텔/주상복합 수집 중...")
        keywords = [
            f"{sigungu} 오피스텔",
            f"{sigungu} 주상복합",
            f"{sigungu} 오피스텔 관리사무소",
            f"{sigungu} 관리사무소",
            f"{sido} {sigungu} 오피스텔",
        ]
        results = []
        for kw in keywords:
            results.extend(self.kakao_places(kw, sido, sigungu))
            time.sleep(0.25)
            results.extend(self.naver_local_places(kw, sido, sigungu))
            time.sleep(0.25)
        results = self.merge_items(results)
        print(f"오피스텔/주상복합 결과: {len(results)}개")
        return results

    def kakao_places(self, keyword: str, sido: str, sigungu: str) -> List[ComplexItem]:
        out = []
        for page in range(1, 4):
            try:
                self.limiter.check_kakao()
                r = self.session.get(
                    KAKAO_KEYWORD_URL,
                    headers=self.kakao_headers,
                    params={"query": keyword, "page": page, "size": 15},
                    timeout=20,
                )
                r.raise_for_status()
                docs = r.json().get("documents", [])
                if not docs:
                    break
                for p in docs:
                    name = p.get("place_name", "").strip()
                    address = p.get("road_address_name") or p.get("address_name") or ""
                    category = p.get("category_name") or ""
                    text = f"{keyword} {name} {category} {address}"
                    if not self.is_target_address(address, sido, sigungu):
                        continue
                    if self.is_trash_place(text):
                        continue
                    if not ("오피스텔" in text or "주상복합" in text or "관리사무소" in text or "관리실" in text):
                        continue
                    phone = normalize_phone(p.get("phone") or "")
                    out.append(ComplexItem(
                        name=name,
                        type="주상복합" if "주상복합" in text else "오피스텔",
                        city=sigungu,
                        district=self.extract_district(address),
                        dong=self.extract_dong(address),
                        address=address,
                        phone=phone,
                        source="카카오 장소검색",
                        verifiedAt="카카오 자동수집",
                        phoneStatus="CONFIRMED" if phone else "UNKNOWN",
                        confidenceScore=90 if phone else 0,
                    ))
                time.sleep(0.15)
            except Exception as e:
                print(f"  카카오 실패 {keyword}: {e}")
                break
        return out

    def naver_local_places(self, keyword: str, sido: str, sigungu: str) -> List[ComplexItem]:
        out = []
        try:
            self.limiter.check_naver()
            r = self.session.get(
                NAVER_LOCAL_URL,
                headers=self.naver_headers,
                params={"query": keyword, "display": 5, "start": 1},
                timeout=20,
            )
            r.raise_for_status()
            for p in r.json().get("items", []):
                name = clean_html(p.get("title", ""))
                address = p.get("roadAddress") or p.get("address") or ""
                category = p.get("category") or ""
                text = f"{keyword} {name} {category} {address}"
                if not self.is_target_address(address, sido, sigungu):
                    continue
                if self.is_trash_place(text):
                    continue
                if not ("오피스텔" in text or "주상복합" in text or "관리사무소" in text or "관리실" in text):
                    continue
                phone = normalize_phone(p.get("telephone") or "")
                out.append(ComplexItem(
                    name=name,
                    type="주상복합" if "주상복합" in text else "오피스텔",
                    city=sigungu,
                    district=self.extract_district(address),
                    dong=self.extract_dong(address),
                    address=address,
                    phone=phone,
                    source="네이버 장소검색",
                    verifiedAt="네이버 자동수집",
                    phoneStatus="CONFIRMED" if phone else "UNKNOWN",
                    confidenceScore=90 if phone else 0,
                ))
        except Exception as e:
            print(f"  네이버 Local 실패 {keyword}: {e}")
        return out

    def enrich_phone(self, item: ComplexItem, skip_web_phone: bool = False) -> ComplexItem:
        keywords = self.phone_keywords(item)
        for kw in keywords:
            phone = self.find_phone_kakao(kw)
            if phone:
                item.phone = phone
                item.verifiedAt = "카카오 전화번호 보강"
                item.phoneStatus = "CONFIRMED"
                item.confidenceScore = max(item.confidenceScore, 90)
                return item
            time.sleep(0.12)

        for kw in keywords:
            phone = self.find_phone_naver_local(kw)
            if phone:
                item.phone = phone
                item.verifiedAt = "네이버 전화번호 보강"
                item.phoneStatus = "CONFIRMED"
                item.confidenceScore = max(item.confidenceScore, 90)
                return item
            time.sleep(0.12)

        if not skip_web_phone:
            for kw in keywords:
                phone = self.find_phone_naver_web_sources(kw)
                if phone:
                    item.phone = phone
                    item.verifiedAt = "웹검색 전화번호 추출"
                    item.phoneStatus = "CANDIDATE"
                    item.confidenceScore = max(item.confidenceScore, 65)
                    return item
                time.sleep(0.12)

        return item

    def find_phone_kakao(self, keyword: str) -> str:
        try:
            self.limiter.check_kakao()
            r = self.session.get(KAKAO_KEYWORD_URL, headers=self.kakao_headers, params={"query": keyword, "page": 1, "size": 15}, timeout=20)
            r.raise_for_status()
            for p in r.json().get("documents", []):
                phone = normalize_phone(p.get("phone") or "")
                if phone:
                    return phone
        except Exception:
            pass
        return ""

    def find_phone_naver_local(self, keyword: str) -> str:
        try:
            self.limiter.check_naver()
            r = self.session.get(NAVER_LOCAL_URL, headers=self.naver_headers, params={"query": keyword, "display": 5, "start": 1}, timeout=20)
            r.raise_for_status()
            for p in r.json().get("items", []):
                phone = normalize_phone(p.get("telephone") or "")
                if phone:
                    return phone
        except Exception:
            pass
        return ""

    def find_phone_naver_web_sources(self, keyword: str) -> str:
        for url in [NAVER_WEB_URL, NAVER_BLOG_URL, NAVER_CAFE_URL]:
            try:
                self.limiter.check_naver()
                r = self.session.get(url, headers=self.naver_headers, params={"query": keyword, "display": 10, "start": 1}, timeout=20)
                r.raise_for_status()
                for p in r.json().get("items", []):
                    text = clean_html(f"{p.get('title','')} {p.get('description','')}")
                    phone = normalize_phone(text)
                    if phone:
                        return phone
            except Exception:
                pass
            time.sleep(0.12)
        return ""

    def phone_keywords(self, item: ComplexItem) -> List[str]:
        clean_name = item.name.replace("오피스텔", "").replace("주상복합", "").replace("관리사무소", "").replace("관리실", "").strip()
        base = [
            f"{item.name} 관리사무소",
            f"{item.name} 관리실",
            f"{item.name} 관리단",
            f"{item.name} 전화번호",
            f"{clean_name} 관리사무소",
            f"{clean_name} 관리실",
            f"{clean_name} 전화번호",
            f"{item.city} {clean_name} 관리사무소",
            f"{item.city} {clean_name} 관리실",
        ]
        if item.district:
            base.append(f"{item.city} {item.district} {clean_name} 관리사무소")
        if item.dong:
            base.append(f"{item.dong} {clean_name} 관리사무소")
        if item.address:
            base.append(f"{item.address} 관리사무소")
            base.append(f"{item.address} 전화번호")
        return list(dict.fromkeys([x.strip() for x in base if x.strip()]))

    def merge_items(self, items: List[ComplexItem]) -> List[ComplexItem]:
        by_key = {}
        for item in items:
            key = item.kaptCode or f"{item.name}_{item.address}_{item.city}_{item.type}"
            old = by_key.get(key)
            if not old:
                by_key[key] = item
            else:
                # 기존보다 정보가 많은 쪽 우선
                if not old.phone and item.phone:
                    old.phone = item.phone
                    old.verifiedAt = item.verifiedAt
                    old.phoneStatus = item.phoneStatus
                    old.confidenceScore = item.confidenceScore
                if not old.address and item.address:
                    old.address = item.address
                if not old.households and item.households:
                    old.households = item.households
        return list(by_key.values())

    def write_region_file(self, sido: str, sigungu: str, items: List[ComplexItem]) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        slug = region_slug(sido, sigungu)
        path = DATA_DIR / f"{slug}.json"

        # 마지막 안전장치: 저장 직전에도 타 시군구 데이터는 절대 저장하지 않음
        safe_items = [x for x in items if self.item_belongs_to_region(x, sido, sigungu)]
        removed = len(items) - len(safe_items)
        if removed > 0:
            print(f"  지역 불일치 항목 제거: {removed}개")

        root = {
            "version": int(time.time()),
            "updatedAt": now_text(),
            "sido": sido,
            "sigungu": sigungu,
            "count": len(safe_items),
            "items": [asdict(x) for x in safe_items],
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(root, f, ensure_ascii=False, indent=2)
        return path

    def _compact(self, text: str) -> str:
        return re.sub(r"\s+", "", text or "")

    def _sido_aliases(self, sido: str) -> List[str]:
        aliases = [sido]
        short = (
            sido
            .replace("특별시", "")
            .replace("광역시", "")
            .replace("특별자치도", "")
            .replace("특별자치시", "")
            .replace("도", "")
        )
        if short and short not in aliases:
            aliases.append(short)
        return aliases

    def _sigungu_aliases(self, sigungu: str) -> List[str]:
        aliases = [sigungu]

        # 세종은 실제 주소에 세종시/세종특별자치시/세종 형태로 섞여 나올 수 있음
        if sigungu == "세종시":
            aliases.append("세종")
            return list(dict.fromkeys(aliases))

        # '중구' -> '중' 같은 1글자 축약은 절대 쓰지 않음
        # '남구/동구/서구/북구/중구'는 전국에 많으므로 반드시 정확한 구 이름만 사용
        if sigungu.endswith("구"):
            return list(dict.fromkeys(aliases))

        short = sigungu[:-1] if sigungu.endswith(("시", "군")) else sigungu
        if len(short) >= 2:
            aliases.append(short)

        return list(dict.fromkeys(aliases))

    def is_target_address(self, address: str, sido: str, sigungu: str) -> bool:
        if not address:
            return False

        text = self._compact(address)

        if sido == "세종특별자치시":
            return "세종" in text

        sido_ok = any(self._compact(x) in text for x in self._sido_aliases(sido))
        sigungu_ok = any(self._compact(x) in text for x in self._sigungu_aliases(sigungu))

        # 핵심: 시도와 시군구가 둘 다 맞아야만 통과
        # 예: 경기도 가평군 생성 중 '경기도 수원시 ...'는 sigungu_ok=False라서 탈락
        return sido_ok and sigungu_ok

    def item_belongs_to_region(self, item: ComplexItem, sido: str, sigungu: str) -> bool:
        # 주소가 있으면 주소 기준으로 엄격 판정
        if item.address:
            return self.is_target_address(item.address, sido, sigungu)

        # 주소가 없을 때만 city 필드 보조 사용
        return (item.city or "") == sigungu

    def is_trash_place(self, text: str) -> bool:
        trash = ["공인중개사", "부동산", "분양", "모델하우스", "홍보관", "숙박", "호텔", "모텔", "고시원", "원룸텔", "리빙텔"]
        return any(x in text for x in trash)

    def address_from_list(self, obj: dict) -> str:
        values = []
        for k in ["as1", "as2", "as3", "as4"]:
            value = str(obj.get(k, "")).strip()
            if value and value.lower() not in ("none", "null"):
                values.append(value)
        return " ".join(values)

    def infer_type(self, type_text: str) -> str:
        if "오피스텔" in type_text:
            return "오피스텔"
        if "주상복합" in type_text:
            return "주상복합"
        return "아파트"

    def extract_sigungu(self, text: str) -> str:
        for cities in REGION_MAP.values():
            for city in cities:
                if city.replace("세종시", "세종") in (text or ""):
                    return city
        return ""

    def extract_district(self, text: str) -> str:
        m = re.search(r"([가-힣0-9]+구)", text or "")
        return m.group(1) if m else ""

    def extract_dong(self, text: str) -> str:
        m = re.search(r"([가-힣0-9]+동|[가-힣0-9]+읍|[가-힣0-9]+면)", text or "")
        return m.group(1) if m else ""


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")



def resolve_region_group(group_name: str) -> List[Tuple[str, str]]:
    """
    --region-group today
    --region-group 0
    --region-group missing
    """
    if not group_name:
        return []

    group_name = group_name.strip().lower()

    if group_name == "today":
        import datetime
        kst = datetime.timezone(datetime.timedelta(hours=9))
        idx = datetime.datetime.now(kst).weekday()
    elif group_name in ("missing", "retry", "missing_retry"):
        idx = 6
    else:
        idx = int(group_name)

    targets = REGION_GROUPS.get(idx, [])

    if targets == ["MISSING_RETRY"]:
        all_regions = [(sido, city) for sido, cities in REGION_MAP.items() for city in cities]
        missing = []
        dummy_config = load_config()
        gen = AptFinderGenerator(dummy_config)
        for sido, sigungu in all_regions:
            count = gen.region_file_count(gen.region_output_path(sido, sigungu))
            if count < 1:
                missing.append((sido, sigungu))
        return missing

    return [
        (sido, city)
        for sido in targets
        for city in REGION_MAP.get(sido, [])
    ]


def resolve_regions(args) -> List[Tuple[str, str]]:
    if getattr(args, "region_group", None):
        return resolve_region_group(args.region_group)
    if args.all:
        return [(sido, city) for sido, cities in REGION_MAP.items() for city in cities]
    if args.region:
        return [parse_region_arg(args.region)]
    if args.sido:
        if args.sido not in REGION_MAP:
            raise SystemExit(f"알 수 없는 시도: {args.sido}")
        return [(args.sido, city) for city in REGION_MAP[args.sido]]
    # 기본 테스트는 성남시 하나만
    return [("경기도", "성남시")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", help='특정 지역만 생성. 예: "경기도|성남시"')
    parser.add_argument("--sido", help='시도 전체 생성. 예: "경기도"')
    parser.add_argument("--all", action="store_true", help="전국 전체 생성")
    parser.add_argument("--skip-web-phone", action="store_true", help="네이버 웹/블로그/카페 전화번호 추출 생략")
    parser.add_argument("--force", action="store_true", help="기존 JSON이 있어도 강제로 다시 생성")
    parser.add_argument("--min-count", type=int, default=1, help="이 개수 이상 들어있는 지역 JSON은 정상으로 보고 건너뜀")
    parser.add_argument("--audit", action="store_true", help="생성하지 않고 현재 output/data 누락 상태만 점검")
    args = parser.parse_args()

    config = load_config()
    regions = resolve_regions(args)

    limiter = ApiCallLimiter(
        max_kakao=args.max_kakao,
        max_naver=args.max_naver,
        max_kapt=args.max_kapt,
    )
    gen = AptFinderGenerator(config, limiter=limiter)

    if args.audit:
        gen.audit_output(regions, min_count=args.min_count)
        gen.rebuild_metadata_from_output()
        return

    gen.run_regions(
        regions,
        skip_web_phone=args.skip_web_phone,
        force=args.force,
        min_count=args.min_count,
        resume=args.resume,
        group_key=args.region_group or args.sido or args.region or ("all" if args.all else "manual")
    )


if __name__ == "__main__":
    main()
