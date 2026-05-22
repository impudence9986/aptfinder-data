# -*- coding: utf-8 -*-
"""
AptFinder 전국/지역별 DB 생성기 - 후보확장 + 복수 전화번호 저장 안정화 버전

핵심 변경:
1) K-apt 밖의 일반 아파트 후보도 카카오/네이버 장소검색으로 추가 수집
2) 오피스텔/주상복합/생활형숙박시설/관리사무소 후보 유지
3) K-apt 번호가 있어도 카카오/네이버/네이버웹 번호를 추가 후보로 계속 수집
4) phoneCandidates 배열 저장 + 기존 phone 필드는 대표번호로 유지
5) 네이버 웹검색 스니펫에서 114On 등 전화번호 후보 추출
"""

import argparse
import os
import json
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


CONFIG_PATH = Path("config.json")
OUTPUT_DIR = Path(".")
DATA_DIR = Path("data")
STATE_PATH = Path("update_state.json")

KAPT_LIST_URL = "https://apis.data.go.kr/1613000/AptListService3/getTotalAptList3"
KAPT_DETAIL_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
NAVER_LOCAL_URL = "https://openapi.naver.com/v1/search/local.json"
NAVER_WEB_URL = "https://openapi.naver.com/v1/search/webkr.json"
NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
NAVER_CAFE_URL = "https://openapi.naver.com/v1/search/cafearticle.json"

PHONE_RE = re.compile(r"(0\d{1,2})[\s\-.)]*(\d{3,4})[\s\-.(]*(\d{4})")


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
        "수원시","화성시","오산시",
        "가평군","고양시","과천시","광명시","광주시","구리시","군포시","김포시",
        "남양주시","동두천시","부천시","성남시","시흥시","안산시","안성시",
        "안양시","양주시","양평군","여주시","연천군","용인시","의왕시",
        "의정부시","이천시","파주시","평택시","포천시","하남시"
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


REGION_GROUPS: Dict[int, List[str]] = {
    0: ["경기도", "서울특별시", "인천광역시"],
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
    sido: str = ""
    district: str = ""
    dong: str = ""
    address: str = ""
    roadAddress: str = ""
    jibunAddress: str = ""
    phone: str = ""
    phones: List[str] = field(default_factory=list)
    phoneCandidates: List[dict] = field(default_factory=list)
    households: str = ""
    source: str = ""
    verifiedAt: str = ""
    detailUpdatedAt: int = 0
    listUpdatedAt: int = 0
    phoneStatus: str = "UNKNOWN"
    reportCount: int = 0
    confidenceScore: int = 0
    lastReportedAt: int = 0
    addressQuality: str = ""
    sharedKey: str = ""


def load_config() -> dict:
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
        (text or "")
        .replace("<b>", "")
        .replace("</b>", "")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .strip()
    )


def normalize_phone(value: str) -> str:
    m = PHONE_RE.search(value or "")
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def extract_all_phones(value: str) -> List[str]:
    out = []
    for m in PHONE_RE.finditer(value or ""):
        out.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return list(dict.fromkeys(out))


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
    pass


class ApiCallLimiter:
    def __init__(
        self,
        max_kakao: int = 999999999,
        max_naver: int = 999999999,
        max_kapt: int = 999999999
    ):
        self.max_kakao = max_kakao
        self.max_naver = max_naver
        self.max_kapt = max_kapt
        self.kakao_used = 0
        self.naver_used = 0
        self.kapt_used = 0

    def check_kakao(self):
        self.kakao_used += 1
        if self.kakao_used > self.max_kakao:
            raise QuotaStop(f"카카오 호출 보호 상한 도달: {self.kakao_used}/{self.max_kakao}")

    def check_naver(self):
        self.naver_used += 1
        if self.naver_used > self.max_naver:
            raise QuotaStop(f"네이버 호출 보호 상한 도달: {self.naver_used}/{self.max_naver}")

    def check_kapt(self):
        self.kapt_used += 1
        if self.kapt_used > self.max_kapt:
            raise QuotaStop(f"K-apt 호출 보호 상한 도달: {self.kapt_used}/{self.max_kapt}")

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
    def __init__(self, config: dict, limiter: Optional[ApiCallLimiter] = None, max_runtime_minutes: int = 330):
        self.config = config
        self.session = requests.Session()
        self.kakao_headers = {"Authorization": f"KakaoAK {config['kakao_rest_key']}"}
        self.naver_headers = {
            "X-Naver-Client-Id": config["naver_client_id"],
            "X-Naver-Client-Secret": config["naver_client_secret"],
        }
        self.kapt_key = config["kapt_service_key"]
        self.limiter = limiter or ApiCallLimiter()
        self.address_cache: Dict[str, dict] = {}
        self.started_at = time.monotonic()
        self.max_runtime_seconds = max(1, int(max_runtime_minutes)) * 60

    def check_runtime_budget(self):
        elapsed = time.monotonic() - self.started_at
        if elapsed >= self.max_runtime_seconds:
            raise QuotaStop(
                f"GitHub Actions 안전정지: {int(elapsed / 60)}분 경과 / "
                f"제한 {int(self.max_runtime_seconds / 60)}분"
            )

    def looks_like_api_quota_limit(self, status_code: int, body: str) -> bool:
        text = (body or "").lower()
        if status_code == 429:
            return True
        if 200 <= status_code < 300:
            return False

        quota_words = [
            "quota", "too many requests", "rate limit", "rate_limit", "ratelimit",
            "exceed", "exceeded", "daily limit", "per day", "qps",
            "throttle", "throttled", "쿼터", "한도", "제한 초과",
            "사용량 초과", "일일 호출", "호출 초과", "트래픽 초과",
        ]

        if status_code in (401, 403, 429, 503):
            return any(w in text for w in quota_words)
        return any(w in text for w in quota_words)

    def api_get(self, url: str, provider: str = "API", **kwargs):
        self.check_runtime_budget()
        response = self.session.get(url, **kwargs)

        try:
            body_preview = response.text[:1000]
        except Exception:
            body_preview = ""

        if self.looks_like_api_quota_limit(response.status_code, body_preview):
            raise QuotaStop(
                f"{provider} 실제 API 사용 제한 감지: HTTP {response.status_code} / {body_preview[:300]}"
            )

        return response

    def kakao_get(self, url: str, **kwargs):
        self.limiter.check_kakao()
        return self.api_get(url, provider="카카오", **kwargs)

    def naver_get(self, url: str, **kwargs):
        self.limiter.check_naver()
        return self.api_get(url, provider="네이버", **kwargs)

    def kapt_get(self, url: str, **kwargs):
        self.limiter.check_kapt()
        return self.api_get(url, provider="K-apt", **kwargs)

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

    def normalize_sido_name(self, value: str) -> str:
        value = (value or "").strip()
        mapping = {
            "서울": "서울특별시",
            "부산": "부산광역시",
            "대구": "대구광역시",
            "인천": "인천광역시",
            "광주": "광주광역시",
            "대전": "대전광역시",
            "울산": "울산광역시",
            "세종": "세종특별자치시",
            "경기": "경기도",
            "강원": "강원특별자치도",
            "충북": "충청북도",
            "충남": "충청남도",
            "전북": "전북특별자치도",
            "전남": "전라남도",
            "경북": "경상북도",
            "경남": "경상남도",
            "제주": "제주특별자치도",
        }
        return mapping.get(value, value)

    def normalize_for_key(self, value: str) -> str:
        value = (value or "").lower().strip()
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"[\-_.·,()\[\]/]", "", value)
        value = value.replace("대한민국", "")
        value = value.replace("번지", "")
        value = value.replace("도로명", "")
        value = value.replace("지번", "")
        value = value.replace("아파트", "")
        value = value.replace("오피스텔", "")
        value = value.replace("주상복합", "")
        value = value.replace("생활형숙박시설", "")
        value = value.replace("관리사무소", "")
        value = value.replace("관리실", "")
        value = value.replace("관리단", "")
        return value

    def make_shared_key(self, item: ComplexItem) -> str:
        parts = [item.sido, item.city, item.name]
        return "_".join([self.normalize_for_key(x) for x in parts if self.normalize_for_key(x)])[:180]

    def make_merge_key(self, item: ComplexItem) -> str:
        code = (item.kaptCode or "").strip()
        if code:
            return f"kapt:{code}"

        name_key = self.normalize_for_key(item.name)
        sido_key = self.normalize_for_key(item.sido)
        city_key = self.normalize_for_key(item.city)
        address_key = self.normalize_for_key(
            item.jibunAddress or item.roadAddress or item.address
        )

        # K-apt 밖 장소검색 후보는 이름이 약간 달라도 같은 지번이면 같은 단지로 합치기 위해
        # 주소가 있으면 type은 키에서 제외한다.
        if address_key:
            return f"{sido_key}_{city_key}_{address_key}"

        type_key = self.normalize_for_key(item.type)
        return f"{sido_key}_{city_key}_{name_key}_{type_key}"

    def build_dual_address(self, road: str, jibun: str, fallback: str = "") -> str:
        road = (road or "").strip()
        jibun = (jibun or "").strip()
        fallback = (fallback or "").strip()

        if road and jibun and self.normalize_for_key(road) != self.normalize_for_key(jibun):
            return f"{road}\n{jibun}"
        if road:
            return road
        if jibun:
            return jibun
        return fallback

    def add_phone_candidate(self, item: ComplexItem, phone: str, source: str, score: int, keyword: str = "") -> bool:
        phone = normalize_phone(phone)
        if not phone:
            return False

        if not isinstance(item.phoneCandidates, list):
            item.phoneCandidates = []
        if not isinstance(item.phones, list):
            item.phones = []

        existed = False
        for c in item.phoneCandidates:
            if c.get("number") == phone:
                existed = True
                old_score = int(c.get("score") or 0)
                if score > old_score:
                    c["score"] = score
                    c["source"] = source
                    c["keyword"] = keyword
                else:
                    sources = c.get("source", "")
                    if source and source not in sources:
                        c["source"] = f"{sources}, {source}".strip(", ")
                break

        if not existed:
            item.phoneCandidates.append({
                "number": phone,
                "source": source,
                "score": int(score),
                "keyword": keyword[:120],
            })

        if phone not in item.phones:
            item.phones.append(phone)

        self.finalize_phone_fields(item)
        return True

    def finalize_phone_fields(self, item: ComplexItem) -> ComplexItem:
        candidates = []
        seen = set()

        if item.phone:
            p = normalize_phone(item.phone)
            if p:
                candidates.append({"number": p, "source": item.verifiedAt or item.source or "기존", "score": int(item.confidenceScore or 50), "keyword": ""})
                seen.add(p)

        for c in item.phoneCandidates or []:
            p = normalize_phone(c.get("number", ""))
            if not p:
                continue
            if p in seen:
                # 같은 번호면 점수/출처 보강
                for old in candidates:
                    if old["number"] == p:
                        if int(c.get("score") or 0) > int(old.get("score") or 0):
                            old["score"] = int(c.get("score") or 0)
                            old["source"] = c.get("source", old.get("source", ""))
                            old["keyword"] = c.get("keyword", old.get("keyword", ""))
                        elif c.get("source") and c.get("source") not in old.get("source", ""):
                            old["source"] = f"{old.get('source','')}, {c.get('source')}".strip(", ")
                        break
                continue
            candidates.append({
                "number": p,
                "source": c.get("source", ""),
                "score": int(c.get("score") or 0),
                "keyword": c.get("keyword", "")[:120],
            })
            seen.add(p)

        # 같은 점수면 K-apt/카카오/네이버Local/114On 스니펫 순으로 안정적 선정
        def source_bonus(src: str) -> int:
            src = src or ""
            if "K-apt" in src or "공공데이터" in src:
                return 5
            if "카카오" in src:
                return 4
            if "네이버 Local" in src or "네이버 장소" in src:
                return 3
            if "114On" in src or "114" in src:
                return 2
            return 0

        candidates.sort(key=lambda c: (int(c.get("score") or 0), source_bonus(c.get("source", ""))), reverse=True)

        item.phoneCandidates = candidates
        item.phones = [c["number"] for c in candidates]

        if candidates:
            item.phone = candidates[0]["number"]
            item.phoneStatus = "CONFIRMED" if int(candidates[0].get("score") or 0) >= 85 else "CANDIDATE"
            item.confidenceScore = max(int(item.confidenceScore or 0), int(candidates[0].get("score") or 0))
            item.verifiedAt = candidates[0].get("source") or item.verifiedAt
        else:
            item.phone = ""
            item.phones = []
            item.phoneCandidates = []
            item.phoneStatus = "UNKNOWN"

        return item

    def kakao_address_search(self, query: str) -> dict:
        query = (query or "").strip()
        if not query:
            return {}

        cache_key = self.normalize_for_key(query)
        if cache_key in self.address_cache:
            return self.address_cache[cache_key]

        try:
            r = self.kakao_get(
                KAKAO_ADDRESS_URL,
                headers=self.kakao_headers,
                params={"query": query},
                timeout=20,
            )
            r.raise_for_status()
            docs = r.json().get("documents", [])
            if not docs:
                self.address_cache[cache_key] = {}
                return {}

            first = docs[0]
            road_obj = first.get("road_address") or {}
            addr_obj = first.get("address") or {}

            result = {
                "roadAddress": (road_obj.get("address_name") or "").strip(),
                "jibunAddress": (addr_obj.get("address_name") or "").strip(),
                "sido": self.normalize_sido_name(addr_obj.get("region_1depth_name") or road_obj.get("region_1depth_name") or ""),
                "cityRaw": (addr_obj.get("region_2depth_name") or road_obj.get("region_2depth_name") or "").strip(),
                "dong": (addr_obj.get("region_3depth_h_name") or addr_obj.get("region_3depth_name") or road_obj.get("region_3depth_name") or "").strip(),
            }
            self.address_cache[cache_key] = result
            return result

        except QuotaStop:
            raise
        except Exception as e:
            print(f"  카카오 주소검색 실패: {query} / {e}")
            self.address_cache[cache_key] = {}
            return {}

    def is_weak_address(self, address: str) -> bool:
        text = (address or "").strip()
        if not text:
            return True

        one_line = re.sub(r"\s+", " ", text).strip()

        if re.search(r"(로|길)\s*\d", one_line):
            return False

        if re.search(r"(동|읍|면)\s*\d", one_line):
            return False

        if re.search(r"(동|읍|면)\s*산\s*\d", one_line):
            return False

        if re.search(r"(동|읍|면)$", one_line):
            return True

        parts = one_line.split()
        if len(parts) <= 3 and re.search(r"(동|읍|면)$", one_line):
            return True

        return False

    def clean_complex_name_for_query(self, name: str) -> str:
        text = (name or "").strip()
        text = re.sub(r"\s+", " ", text)
        for token in ["아파트", "오피스텔", "주상복합", "생활형숙박시설", "관리사무소", "관리실", "관리단"]:
            text = text.replace(token, "")
        return text.strip()

    def address_score(self, road: str, jibun: str, sido: str, sigungu: str, name: str = "") -> int:
        road = (road or "").strip()
        jibun = (jibun or "").strip()
        display = self.build_dual_address(road, jibun, "")

        if not display:
            return 0

        if not self.is_target_address(display, sido, sigungu):
            return 0

        score = 10

        if road:
            score += 30
        if jibun:
            score += 30

        if road and re.search(r"(로|길)\s*\d", road):
            score += 25

        if jibun and re.search(r"(동|읍|면)\s*(산\s*)?\d", jibun):
            score += 25

        if not self.is_weak_address(display):
            score += 25
        else:
            score -= 35

        name_key = self.normalize_for_key(name)
        display_key = self.normalize_for_key(display)

        if name_key and name_key in display_key:
            score += 10

        return score

    def kakao_keyword_address_search(self, query: str, sido: str, sigungu: str, name: str = "") -> dict:
        query = (query or "").strip()
        if not query:
            return {}

        try:
            r = self.kakao_get(
                KAKAO_KEYWORD_URL,
                headers=self.kakao_headers,
                params={"query": query, "page": 1, "size": 15},
                timeout=20,
            )
            r.raise_for_status()

            docs = r.json().get("documents", [])
            best = {}
            best_score = 0

            for p in docs:
                road = (p.get("road_address_name") or "").strip()
                jibun = (p.get("address_name") or "").strip()
                place_name = (p.get("place_name") or "").strip()
                category = (p.get("category_name") or "").strip()

                text = f"{place_name} {category} {road} {jibun}"

                if self.is_trash_place(text):
                    continue

                display = self.build_dual_address(road, jibun, "")
                if not self.is_target_address(display, sido, sigungu):
                    continue

                score = self.address_score(road, jibun, sido, sigungu, name)

                name_key = self.normalize_for_key(name)
                place_key = self.normalize_for_key(place_name)

                if name_key and place_key:
                    if name_key == place_key:
                        score += 30
                    elif name_key in place_key or place_key in name_key:
                        score += 20

                if any(x in text for x in ["아파트", "오피스텔", "주상복합", "생활형숙박시설", "관리사무소", "관리실"]):
                    score += 10

                if score > best_score:
                    best_score = score
                    best = {
                        "roadAddress": road,
                        "jibunAddress": jibun,
                        "sido": sido,
                        "cityRaw": sigungu,
                        "dong": self.extract_dong(jibun or road),
                        "score": score,
                    }

            return best if best_score >= 45 else {}

        except QuotaStop:
            raise
        except Exception as e:
            print(f"  카카오 장소주소검색 실패: {query} / {e}")
            return {}

    def naver_local_address_search(self, query: str, sido: str, sigungu: str, name: str = "") -> dict:
        query = (query or "").strip()
        if not query:
            return {}

        try:
            r = self.naver_get(
                NAVER_LOCAL_URL,
                headers=self.naver_headers,
                params={"query": query, "display": 10, "start": 1},
                timeout=20,
            )
            r.raise_for_status()

            items = r.json().get("items", [])
            best = {}
            best_score = 0

            for p in items:
                place_name = clean_html(p.get("title", ""))
                road = (p.get("roadAddress") or "").strip()
                jibun = (p.get("address") or "").strip()
                category = (p.get("category") or "").strip()

                text = f"{place_name} {category} {road} {jibun}"

                if self.is_trash_place(text):
                    continue

                display = self.build_dual_address(road, jibun, "")
                if not self.is_target_address(display, sido, sigungu):
                    continue

                score = self.address_score(road, jibun, sido, sigungu, name)

                name_key = self.normalize_for_key(name)
                place_key = self.normalize_for_key(place_name)

                if name_key and place_key:
                    if name_key == place_key:
                        score += 30
                    elif name_key in place_key or place_key in name_key:
                        score += 20

                if any(x in text for x in ["아파트", "오피스텔", "주상복합", "생활형숙박시설", "관리사무소", "관리실"]):
                    score += 10

                if score > best_score:
                    best_score = score
                    best = {
                        "roadAddress": road,
                        "jibunAddress": jibun,
                        "sido": sido,
                        "cityRaw": sigungu,
                        "dong": self.extract_dong(jibun or road),
                        "score": score,
                    }

            return best if best_score >= 45 else {}

        except QuotaStop:
            raise
        except Exception as e:
            print(f"  네이버 Local 주소검색 실패: {query} / {e}")
            return {}

    def build_address_queries(self, raw_address: str, name: str, sido: str, sigungu: str) -> List[str]:
        raw_address = (raw_address or "").strip()
        name = (name or "").strip()
        clean_name = self.clean_complex_name_for_query(name)

        queries = []
        weak = self.is_weak_address(raw_address)

        if name:
            queries.extend([
                f"{sido} {sigungu} {name}",
                f"{sido} {sigungu} {name} 아파트",
                f"{sido} {sigungu} {name} 관리사무소",
            ])

        if clean_name and clean_name != name:
            queries.extend([
                f"{sido} {sigungu} {clean_name}",
                f"{sido} {sigungu} {clean_name} 아파트",
                f"{sido} {sigungu} {clean_name} 관리사무소",
            ])

        if raw_address and not weak:
            queries.insert(0, raw_address)
            if name:
                queries.append(f"{raw_address} {name}".strip())
        elif raw_address:
            if name:
                queries.append(f"{sido} {sigungu} {name} {raw_address}")
            queries.append(raw_address)

        return list(dict.fromkeys([q.strip() for q in queries if q.strip()]))

    def complete_dual_address(
        self,
        road: str,
        jibun: str,
        raw_address: str,
        name: str,
        sido: str,
        sigungu: str
    ) -> Tuple[str, str]:
        road = (road or "").strip()
        jibun = (jibun or "").strip()
        raw_address = (raw_address or "").strip()
        name = (name or "").strip()

        if road and jibun:
            return road, jibun

        queries = []

        if road:
            queries.extend([road, f"{road} {name}".strip(), f"{sido} {sigungu} {road}".strip()])

        if jibun:
            queries.extend([jibun, f"{jibun} {name}".strip(), f"{sido} {sigungu} {jibun}".strip()])

        if raw_address:
            queries.extend([raw_address, f"{raw_address} {name}".strip()])

        if name:
            clean_name = self.clean_complex_name_for_query(name)
            queries.extend([
                f"{sido} {sigungu} {name}".strip(),
                f"{sido} {sigungu} {name} 아파트".strip(),
                f"{sido} {sigungu} {name} 관리사무소".strip(),
            ])
            if clean_name and clean_name != name:
                queries.extend([
                    f"{sido} {sigungu} {clean_name}".strip(),
                    f"{sido} {sigungu} {clean_name} 아파트".strip(),
                    f"{sido} {sigungu} {clean_name} 관리사무소".strip(),
                ])

        queries = list(dict.fromkeys([q for q in queries if q]))

        def accept_candidate(candidate_road: str, candidate_jibun: str) -> bool:
            display = self.build_dual_address(candidate_road, candidate_jibun, "")
            if not display:
                return False
            if not self.is_target_address(display, sido, sigungu):
                return False
            return True

        def merge_candidate(candidate: dict) -> bool:
            nonlocal road, jibun

            candidate_road = (candidate.get("roadAddress") or "").strip()
            candidate_jibun = (candidate.get("jibunAddress") or "").strip()

            if not accept_candidate(candidate_road, candidate_jibun):
                return False

            changed = False

            if not road and candidate_road:
                road = candidate_road
                changed = True

            if not jibun and candidate_jibun:
                jibun = candidate_jibun
                changed = True

            return changed

        for q in queries:
            if road and jibun:
                break
            candidate = self.naver_local_address_search(q, sido, sigungu, name)
            if merge_candidate(candidate) and road and jibun:
                break
            time.sleep(0.05)

        for q in queries:
            if road and jibun:
                break
            candidate = self.kakao_keyword_address_search(q, sido, sigungu, name)
            if merge_candidate(candidate) and road and jibun:
                break
            time.sleep(0.05)

        for q in queries:
            if road and jibun:
                break
            candidate = self.kakao_address_search(q)
            if merge_candidate(candidate) and road and jibun:
                break
            time.sleep(0.05)

        return road, jibun

    def resolve_dual_address(self, raw_address: str, name: str, sido: str, sigungu: str) -> Tuple[str, str, str, str, str, str]:
        raw_address = (raw_address or "").strip()
        name = (name or "").strip()

        queries = self.build_address_queries(raw_address, name, sido, sigungu)

        best_result = {}
        best_score = 0

        for q in queries:
            result = self.kakao_keyword_address_search(q, sido, sigungu, name)
            if result:
                score = int(result.get("score") or 0)
                if score > best_score:
                    best_result = result
                    best_score = score

                if score >= 95 and result.get("roadAddress") and result.get("jibunAddress"):
                    break

            time.sleep(0.08)

        if best_score < 95 or not best_result.get("roadAddress") or not best_result.get("jibunAddress"):
            for q in queries:
                result = self.naver_local_address_search(q, sido, sigungu, name)
                if result:
                    score = int(result.get("score") or 0)
                    if score > best_score:
                        best_result = result
                        best_score = score

                    if score >= 95 and result.get("roadAddress") and result.get("jibunAddress"):
                        break

                time.sleep(0.08)

        if best_score < 80 or not best_result.get("roadAddress") or not best_result.get("jibunAddress"):
            for q in queries:
                result = self.kakao_address_search(q)
                road = result.get("roadAddress", "")
                jibun = result.get("jibunAddress", "")

                score = self.address_score(road, jibun, sido, sigungu, name)

                if score > best_score:
                    best_result = {**result, "score": score}
                    best_score = score

                if score >= 90 and road and jibun:
                    break

                time.sleep(0.08)

        if not best_result:
            return (
                raw_address, "", "", sido,
                self.extract_district(raw_address),
                self.extract_dong(raw_address),
            )

        road = (best_result.get("roadAddress") or "").strip()
        jibun = (best_result.get("jibunAddress") or "").strip()

        road, jibun = self.complete_dual_address(
            road=road,
            jibun=jibun,
            raw_address=raw_address,
            name=name,
            sido=sido,
            sigungu=sigungu,
        )

        display = self.build_dual_address(road, jibun, raw_address)

        if self.is_weak_address(display) and raw_address and not self.is_weak_address(raw_address):
            display = raw_address
            road = raw_address if re.search(r"(로|길)\s*\d", raw_address) else ""
            jibun = raw_address if re.search(r"(동|읍|면)\s*(산\s*)?\d", raw_address) else ""

        fixed_sido = best_result.get("sido") or sido
        city_raw = best_result.get("cityRaw", "")

        district = ""
        if " " in city_raw:
            district = city_raw.split(" ", 1)[1].strip()

        if not district:
            district = self.extract_district(display)

        dong = best_result.get("dong") or self.extract_dong(display)

        return display, road, jibun, fixed_sido, district, dong

    def normalize_item_address(self, item: ComplexItem, sido: str, sigungu: str) -> ComplexItem:
        display, road, jibun, fixed_sido, district, dong = self.resolve_dual_address(
            item.address,
            item.name,
            sido,
            sigungu,
        )

        item.sido = fixed_sido or sido
        item.city = sigungu
        item.address = display or item.address
        item.roadAddress = road
        item.jibunAddress = jibun

        if not item.district:
            item.district = district
        if not item.dong:
            item.dong = dong

        if road and jibun:
            item.addressQuality = "ROAD_AND_JIBUN"
        elif road:
            item.addressQuality = "ROAD_ONLY"
        elif jibun:
            item.addressQuality = "JIBUN_ONLY"
        else:
            item.addressQuality = "RAW"

        item.sharedKey = self.make_shared_key(item)
        return item

    def should_skip_region(self, sido: str, sigungu: str, force: bool, min_count: int) -> bool:
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

                    self.save_state(
                        group_key,
                        completed,
                        [(sido, sigungu)] + remaining_after_current,
                        "stopped",
                        reason=f"지역 처리 실패: {sido}|{sigungu} / {e}"
                    )

                    self.rebuild_metadata_from_output()
                    print("\n지역 처리 실패로 중단했습니다.")
                    print("다음 실행 때 --resume 옵션으로 이어서 처리됩니다.")
                    print(f"남은 지역: {1 + len(remaining_after_current)}개")
                    return

            self.rebuild_metadata_from_output()
            self.clear_state_if_done()

            print("\n전체 완료")
            print(f"처리: {processed}개 / 건너뜀: {skipped}개 / 실패: {failed}개")
            print(f"GitHub 업로드 대상 폴더: {OUTPUT_DIR.resolve()}")

        except QuotaStop as e:
            current_index = processed + skipped
            remaining = regions[current_index:]
            self.save_state(group_key, completed, remaining, "stopped", reason=str(e))
            self.rebuild_metadata_from_output()
            print(f"\n호출량 보호로 정상 중단: {e}")
            print("다음 실행 때 --resume 옵션으로 이어서 처리됩니다.")
            print(f"남은 지역: {len(remaining)}개")

    def build_region(self, sido: str, sigungu: str, skip_web_phone: bool = False) -> List[ComplexItem]:
        apt_items = self.fetch_kapt_region(sido, sigungu)
        extra_items = self.collect_extra_complexes(sido, sigungu)

        merged = self.merge_items(apt_items + extra_items)

        print(f"주소 보강 시작: {len(merged)}개")
        addressed = []
        for i, item in enumerate(merged, start=1):
            item = self.normalize_item_address(item, sido, sigungu)
            addressed.append(item)
            if i % 20 == 0 or i == len(merged):
                print(f"  주소 보강 {i}/{len(merged)}")

        merged = self.merge_items(addressed)

        print(f"전화번호 후보 수집 시작: {len(merged)}개")
        enriched = []
        for i, item in enumerate(merged, start=1):
            # 기존 phone이 있어도 반드시 후보 수집한다.
            item = self.enrich_phone(item, skip_web_phone=skip_web_phone)
            item = self.finalize_phone_fields(item)
            enriched.append(item)
            if i % 20 == 0 or i == len(merged):
                print(f"  전화번호 후보 수집 {i}/{len(merged)}")

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
                r = self.kapt_get(KAPT_LIST_URL, params=params, timeout=60)
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

            except QuotaStop:
                raise
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
            r = self.kapt_get(KAPT_DETAIL_URL, params=params, timeout=40)
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

            out = ComplexItem(
                kaptCode=kapt_code,
                name=name,
                type=self.infer_type(item.get("codeAptNm", "")),
                city=sigungu,
                sido=sido,
                district=self.extract_district(address),
                dong=self.extract_dong(address),
                address=address,
                phone=phone,
                households=households if households.isdigit() else "",
                source="공공데이터 K-apt",
                verifiedAt="공공데이터 K-apt",
                detailUpdatedAt=now,
                listUpdatedAt=now,
                phoneStatus="CONFIRMED" if phone else "UNKNOWN",
                confidenceScore=100 if phone else 0,
            )
            if phone:
                self.add_phone_candidate(out, phone, "공공데이터 K-apt", 100, "kaptTel")
            return out

        except QuotaStop:
            raise
        except Exception as e:
            print(f"  K-apt 상세 실패: {kapt_code} / {e}")
            return self.item_from_kapt_list(fallback, now, sido, sigungu)

    def item_from_kapt_list(self, obj: dict, now: int, sido: str, sigungu: str) -> ComplexItem:
        address = self.address_from_list(obj)
        return ComplexItem(
            kaptCode=obj.get("kaptCode") or "",
            name=obj.get("kaptName") or obj.get("kaptNm") or "",
            type="아파트",
            city=sigungu,
            sido=sido,
            district=self.extract_district(address),
            dong=self.extract_dong(address),
            address=address,
            source="공공데이터 K-apt",
            verifiedAt="목록정보",
            listUpdatedAt=now,
        )

    def collect_extra_complexes(self, sido: str, sigungu: str) -> List[ComplexItem]:
        print("지도/검색 기반 추가 후보 수집 중...")

        # 너무 넓은 일반 아파트 검색은 많아질 수 있지만,
        # K-apt 밖의 소규모 아파트/빌라형 단지 누락을 줄이기 위해 포함한다.
        keywords = [
            f"{sigungu} 아파트",
            f"{sigungu} 아파트 관리사무소",
            f"{sigungu} 관리사무소",
            f"{sigungu} 오피스텔",
            f"{sigungu} 주상복합",
            f"{sigungu} 오피스텔 관리사무소",
            f"{sigungu} 주상복합 관리사무소",
            f"{sigungu} 생활형숙박시설",
            f"{sido} {sigungu} 아파트",
            f"{sido} {sigungu} 아파트 관리사무소",
            f"{sido} {sigungu} 오피스텔",
            f"{sido} {sigungu} 주상복합",
            f"{sido} {sigungu} 생활형숙박시설",
        ]

        results = []
        for kw in list(dict.fromkeys(keywords)):
            results.extend(self.kakao_places(kw, sido, sigungu))
            time.sleep(0.25)
            results.extend(self.naver_local_places(kw, sido, sigungu))
            time.sleep(0.25)

        results = self.merge_items(results)
        print(f"추가 후보 결과: {len(results)}개")
        return results

    # 기존 이름으로 호출해도 동작하도록 별칭 유지
    def collect_officetels(self, sido: str, sigungu: str) -> List[ComplexItem]:
        return self.collect_extra_complexes(sido, sigungu)

    def infer_place_type(self, text: str) -> str:
        if "생활형숙박시설" in text:
            return "생활형숙박시설"
        if "오피스텔" in text:
            return "오피스텔"
        if "주상복합" in text:
            return "주상복합"
        return "아파트"

    def is_complex_candidate_text(self, text: str) -> bool:
        text = text or ""
        include_words = [
            "아파트", "오피스텔", "주상복합", "생활형숙박시설",
            "관리사무소", "관리실", "관리단",
        ]
        return any(x in text for x in include_words)

    def kakao_places(self, keyword: str, sido: str, sigungu: str) -> List[ComplexItem]:
        out = []
        for page in range(1, 4):
            try:
                r = self.kakao_get(
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
                    road = p.get("road_address_name") or ""
                    jibun = p.get("address_name") or ""
                    address = road or jibun
                    category = p.get("category_name") or ""
                    text = f"{keyword} {name} {category} {address}"

                    if not self.is_target_address(address, sido, sigungu):
                        continue
                    if self.is_trash_place(text):
                        continue
                    if not self.is_complex_candidate_text(text):
                        continue

                    phone = normalize_phone(p.get("phone") or "")
                    item = ComplexItem(
                        name=name,
                        type=self.infer_place_type(text),
                        city=sigungu,
                        sido=sido,
                        district=self.extract_district(address),
                        dong=self.extract_dong(address),
                        address=self.build_dual_address(road, jibun, address),
                        roadAddress=road,
                        jibunAddress=jibun,
                        phone=phone,
                        source="카카오 장소검색",
                        verifiedAt="카카오 장소검색",
                        phoneStatus="CONFIRMED" if phone else "UNKNOWN",
                        confidenceScore=90 if phone else 0,
                        addressQuality="ROAD_AND_JIBUN" if road and jibun else ("ROAD_ONLY" if road else ("JIBUN_ONLY" if jibun else "RAW")),
                    )
                    if phone:
                        self.add_phone_candidate(item, phone, "카카오 장소검색", 90, keyword)
                    out.append(item)
                time.sleep(0.15)
            except QuotaStop:
                raise
            except Exception as e:
                print(f"  카카오 실패 {keyword}: {e}")
                break
        return out

    def naver_local_places(self, keyword: str, sido: str, sigungu: str) -> List[ComplexItem]:
        out = []
        try:
            r = self.naver_get(
                NAVER_LOCAL_URL,
                headers=self.naver_headers,
                params={"query": keyword, "display": 10, "start": 1},
                timeout=20,
            )
            r.raise_for_status()
            for p in r.json().get("items", []):
                name = clean_html(p.get("title", ""))
                road = (p.get("roadAddress") or "").strip()
                jibun = (p.get("address") or "").strip()
                address = road or jibun
                category = p.get("category") or ""
                text = f"{keyword} {name} {category} {address}"

                if not self.is_target_address(address, sido, sigungu):
                    continue
                if self.is_trash_place(text):
                    continue
                if not self.is_complex_candidate_text(text):
                    continue

                phone = normalize_phone(p.get("telephone") or "")
                item = ComplexItem(
                    name=name,
                    type=self.infer_place_type(text),
                    city=sigungu,
                    sido=sido,
                    district=self.extract_district(address),
                    dong=self.extract_dong(address),
                    address=self.build_dual_address(road, jibun, address),
                    roadAddress=road,
                    jibunAddress=jibun,
                    phone=phone,
                    source="네이버 장소검색",
                    verifiedAt="네이버 장소검색",
                    phoneStatus="CONFIRMED" if phone else "UNKNOWN",
                    confidenceScore=90 if phone else 0,
                    addressQuality="ROAD_AND_JIBUN" if road and jibun else ("ROAD_ONLY" if road else ("JIBUN_ONLY" if jibun else "RAW")),
                )
                if phone:
                    self.add_phone_candidate(item, phone, "네이버 Local", 90, keyword)
                out.append(item)
        except QuotaStop:
            raise
        except Exception as e:
            print(f"  네이버 Local 실패 {keyword}: {e}")
        return out

    def enrich_phone(self, item: ComplexItem, skip_web_phone: bool = False) -> ComplexItem:
        # 기존 대표번호도 후보에 포함
        if item.phone:
            self.add_phone_candidate(item, item.phone, item.verifiedAt or item.source or "기존번호", item.confidenceScore or 70, "existing")

        keywords = self.phone_keywords(item)

        for kw in keywords:
            found = self.find_phone_kakao_all(kw)
            for phone in found:
                self.add_phone_candidate(item, phone, "카카오 전화번호 보강", 90, kw)
            time.sleep(0.12)

        for kw in keywords:
            found = self.find_phone_naver_local_all(kw)
            for phone in found:
                self.add_phone_candidate(item, phone, "네이버 Local 전화번호 보강", 90, kw)
            time.sleep(0.12)

        if not skip_web_phone:
            for kw in keywords:
                found = self.find_phone_naver_web_sources_all(kw)
                for phone, source in found:
                    self.add_phone_candidate(item, phone, source, 75 if "114" in source else 65, kw)
                time.sleep(0.12)

        return self.finalize_phone_fields(item)

    def find_phone_kakao_all(self, keyword: str) -> List[str]:
        out = []
        try:
            r = self.kakao_get(
                KAKAO_KEYWORD_URL,
                headers=self.kakao_headers,
                params={"query": keyword, "page": 1, "size": 15},
                timeout=20
            )
            r.raise_for_status()
            for p in r.json().get("documents", []):
                phone = normalize_phone(p.get("phone") or "")
                if phone:
                    out.append(phone)
        except QuotaStop:
            raise
        except Exception as e:
            print(f"  카카오 전화검색 실패: {keyword} / {e}")
        return list(dict.fromkeys(out))

    def find_phone_naver_local_all(self, keyword: str) -> List[str]:
        out = []
        try:
            r = self.naver_get(
                NAVER_LOCAL_URL,
                headers=self.naver_headers,
                params={"query": keyword, "display": 10, "start": 1},
                timeout=20
            )
            r.raise_for_status()
            for p in r.json().get("items", []):
                phone = normalize_phone(p.get("telephone") or "")
                if phone:
                    out.append(phone)
        except QuotaStop:
            raise
        except Exception as e:
            print(f"  네이버 전화검색 실패: {keyword} / {e}")
        return list(dict.fromkeys(out))

    def find_phone_naver_web_sources_all(self, keyword: str) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for url, api_name in [
            (NAVER_WEB_URL, "네이버 웹검색"),
            (NAVER_BLOG_URL, "네이버 블로그검색"),
            (NAVER_CAFE_URL, "네이버 카페검색"),
        ]:
            try:
                r = self.naver_get(
                    url,
                    headers=self.naver_headers,
                    params={"query": keyword, "display": 10, "start": 1},
                    timeout=20
                )
                r.raise_for_status()
                for p in r.json().get("items", []):
                    title = clean_html(p.get("title", ""))
                    desc = clean_html(p.get("description", ""))
                    link = p.get("link", "") or ""
                    text = f"{title} {desc}"

                    source = api_name
                    if "114" in title or "114" in desc or "114.co.kr" in link:
                        source = "114On/네이버 스니펫"

                    for phone in extract_all_phones(text):
                        out.append((phone, source))

            except QuotaStop:
                raise
            except Exception as e:
                print(f"  네이버 웹 전화검색 실패: {keyword} / {e}")
            time.sleep(0.12)

        # 번호+출처 기준 중복 제거
        seen = set()
        dedup = []
        for phone, source in out:
            key = (phone, source)
            if key in seen:
                continue
            seen.add(key)
            dedup.append((phone, source))
        return dedup

    # 구버전 함수명 호환
    def find_phone_kakao(self, keyword: str) -> str:
        phones = self.find_phone_kakao_all(keyword)
        return phones[0] if phones else ""

    def find_phone_naver_local(self, keyword: str) -> str:
        phones = self.find_phone_naver_local_all(keyword)
        return phones[0] if phones else ""

    def find_phone_naver_web_sources(self, keyword: str) -> str:
        found = self.find_phone_naver_web_sources_all(keyword)
        return found[0][0] if found else ""

    def phone_keywords(self, item: ComplexItem) -> List[str]:
        clean_name = (
            item.name
            .replace("아파트", "")
            .replace("오피스텔", "")
            .replace("주상복합", "")
            .replace("생활형숙박시설", "")
            .replace("관리사무소", "")
            .replace("관리실", "")
            .replace("관리단", "")
            .strip()
        )

        base = [
            f"{item.name} 관리사무소",
            f"{item.name} 관리실",
            f"{item.name} 관리단",
            f"{item.name} 전화번호",
            f"{clean_name} 관리사무소",
            f"{clean_name} 관리실",
            f"{clean_name} 관리단",
            f"{clean_name} 전화번호",
            f"{item.city} {clean_name} 관리사무소",
            f"{item.city} {clean_name} 관리실",
        ]

        if item.district:
            base.append(f"{item.city} {item.district} {clean_name} 관리사무소")
        if item.dong:
            base.append(f"{item.dong} {clean_name} 관리사무소")

        address_candidates = []
        if item.roadAddress:
            address_candidates.append(item.roadAddress)
        if item.jibunAddress:
            address_candidates.append(item.jibunAddress)
        if item.address:
            address_candidates.extend([x.strip() for x in item.address.splitlines() if x.strip()])

        for addr in list(dict.fromkeys(address_candidates)):
            base.append(f"{addr} 관리사무소")
            base.append(f"{addr} 관리실")
            base.append(f"{addr} 전화번호")

        return list(dict.fromkeys([x.strip() for x in base if x.strip()]))

    def merge_items(self, items: List[ComplexItem]) -> List[ComplexItem]:
        by_key = {}

        for item in items:
            if not item:
                continue

            self.finalize_phone_fields(item)

            key = self.make_merge_key(item)
            old = by_key.get(key)

            if not old:
                by_key[key] = item
                continue

            # 후보 번호 전부 합치기
            for c in item.phoneCandidates or []:
                self.add_phone_candidate(
                    old,
                    c.get("number", ""),
                    c.get("source", ""),
                    int(c.get("score") or 0),
                    c.get("keyword", "")
                )

            # 대표번호/점수 갱신은 finalize에서 처리
            self.finalize_phone_fields(old)

            # 이름은 더 짧고 일반적인 이름보다 관리사무소가 붙지 않은 이름 우선
            if item.name and (not old.name or ("관리" in old.name and "관리" not in item.name)):
                old.name = item.name

            # type은 아파트보다 구체 타입 우선
            if old.type == "아파트" and item.type in ("오피스텔", "주상복합", "생활형숙박시설"):
                old.type = item.type

            # 주소는 도로명+지번 둘 다 있는 데이터 우선
            if not old.address and item.address:
                old.address = item.address
            if not old.roadAddress and item.roadAddress:
                old.roadAddress = item.roadAddress
            if not old.jibunAddress and item.jibunAddress:
                old.jibunAddress = item.jibunAddress

            if old.addressQuality != "ROAD_AND_JIBUN" and item.addressQuality == "ROAD_AND_JIBUN":
                old.address = item.address
                old.roadAddress = item.roadAddress
                old.jibunAddress = item.jibunAddress
                old.addressQuality = item.addressQuality

            if not old.households and item.households:
                old.households = item.households
            if not old.sido and item.sido:
                old.sido = item.sido
            if not old.city and item.city:
                old.city = item.city
            if not old.district and item.district:
                old.district = item.district
            if not old.dong and item.dong:
                old.dong = item.dong
            if not old.sharedKey and item.sharedKey:
                old.sharedKey = item.sharedKey

            if item.source and item.source not in old.source:
                old.source = f"{old.source}, {item.source}".strip(", ") if old.source else item.source

            self.finalize_phone_fields(old)

        return list(by_key.values())

    def write_region_file(self, sido: str, sigungu: str, items: List[ComplexItem]) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        slug = region_slug(sido, sigungu)
        path = DATA_DIR / f"{slug}.json"

        safe_items = [x for x in items if self.item_belongs_to_region(x, sido, sigungu)]
        removed = len(items) - len(safe_items)
        if removed > 0:
            print(f"  지역 불일치 항목 제거: {removed}개")

        for item in safe_items:
            item.sido = item.sido or sido
            item.city = item.city or sigungu
            item.sharedKey = item.sharedKey or self.make_shared_key(item)
            self.finalize_phone_fields(item)

        safe_items.sort(key=lambda x: (self.normalize_for_key(x.dong), self.normalize_for_key(x.name)))

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

        if sigungu == "세종시":
            aliases.append("세종")
            return list(dict.fromkeys(aliases))

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

        return sido_ok and sigungu_ok

    def item_belongs_to_region(self, item: ComplexItem, sido: str, sigungu: str) -> bool:
        if item.address:
            return self.is_target_address(item.address, sido, sigungu)
        return (item.city or "") == sigungu

    def is_trash_place(self, text: str) -> bool:
        trash = [
            "공인중개사", "부동산", "분양", "모델하우스", "홍보관",
            "숙박", "호텔", "모텔", "고시원", "원룸텔", "리빙텔",
            "인테리어", "청소", "이사", "도배", "장판", "누수", "설비",
        ]
        return any(x in (text or "") for x in trash)

    def address_from_list(self, obj: dict) -> str:
        values = []
        for k in ["as1", "as2", "as3", "as4"]:
            value = str(obj.get(k, "")).strip()
            if value and value.lower() not in ("none", "null"):
                values.append(value)
        return " ".join(values)

    def infer_type(self, type_text: str) -> str:
        if "생활형숙박시설" in (type_text or ""):
            return "생활형숙박시설"
        if "오피스텔" in (type_text or ""):
            return "오피스텔"
        if "주상복합" in (type_text or ""):
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


def all_regions_ordered() -> List[Tuple[str, str]]:
    ordered_sidos = ["경기도"] + [sido for sido in REGION_MAP.keys() if sido != "경기도"]
    return [
        (sido, city)
        for sido in ordered_sidos
        for city in REGION_MAP.get(sido, [])
    ]


def resolve_region_group(group_name: str) -> List[Tuple[str, str]]:
    group_name = (group_name or "all").strip().lower()

    if group_name in ("today", "all", "full", "전국"):
        return all_regions_ordered()

    if group_name in ("missing", "retry", "missing_retry"):
        missing = []
        dummy_config = load_config()
        gen = AptFinderGenerator(dummy_config)
        for sido, sigungu in all_regions_ordered():
            count = gen.region_file_count(gen.region_output_path(sido, sigungu))
            if count < 1:
                missing.append((sido, sigungu))
        return missing

    idx = int(group_name)
    targets = REGION_GROUPS.get(idx, [])

    if targets == ["MISSING_RETRY"]:
        missing = []
        dummy_config = load_config()
        gen = AptFinderGenerator(dummy_config)
        for sido, sigungu in all_regions_ordered():
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
        return all_regions_ordered()
    if args.region:
        return [parse_region_arg(args.region)]
    if args.sido:
        if args.sido not in REGION_MAP:
            raise SystemExit(f"알 수 없는 시도: {args.sido}")
        return [(args.sido, city) for city in REGION_MAP[args.sido]]
    return [("경기도", "성남시")]


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--region", help='특정 지역만 생성. 예: "경기도|성남시"')
    parser.add_argument("--sido", help='시도 전체 생성. 예: "경기도"')
    parser.add_argument("--all", action="store_true", help="전국 전체 생성")

    parser.add_argument(
        "--skip-web-phone",
        action="store_true",
        help="네이버 웹/블로그/카페 전화번호 추출 생략"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 JSON이 있어도 강제로 다시 생성"
    )

    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="이 개수 이상 들어있는 지역 JSON은 정상으로 보고 건너뜀"
    )

    parser.add_argument(
        "--audit",
        action="store_true",
        help="생성하지 않고 현재 output/data 누락 상태만 점검"
    )

    parser.add_argument(
        "--region-group",
        help="자동 생성. today/all은 전국 전체를 순서대로 처리하고, 한도 도달 시 다음 실행에서 이어서 처리"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="이전 중단 지점부터 이어서 실행"
    )

    parser.add_argument(
        "--max-kakao",
        type=int,
        default=999999999,
        help="카카오 호출 보호 상한"
    )

    parser.add_argument(
        "--max-naver",
        type=int,
        default=999999999,
        help="네이버 호출 보호 상한"
    )

    parser.add_argument(
        "--max-kapt",
        type=int,
        default=999999999,
        help="K-apt 호출 보호 상한"
    )

    parser.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=330,
        help="GitHub Actions 강제 종료 전 안전정지 시간(분). 기본 330분"
    )

    args = parser.parse_args()

    config = load_config()
    regions = resolve_regions(args)

    limiter = ApiCallLimiter(
        max_kakao=args.max_kakao,
        max_naver=args.max_naver,
        max_kapt=args.max_kapt,
    )

    gen = AptFinderGenerator(config, limiter=limiter, max_runtime_minutes=args.max_runtime_minutes)

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
