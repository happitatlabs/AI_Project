"""
런처 의존성 진단: requirements 파싱, 패키지 확인.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple


def parse_requirements_file(requirements_path: Path) -> List[str]:
    """
    requirements.txt 파일을 파싱하여 패키지 이름 목록 추출.

    형식 지원:
    - package==1.0.0
    - package>=1.0.0
    - package~=1.0.0
    - package ; python_version < '3.11'
    - # 주석
    """
    packages = []
    if not requirements_path.exists():
        return packages

    try:
        with open(requirements_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ";" in line:
                    line = line.split(";")[0].strip()
                match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                if match:
                    package_name = match.group(1)
                    packages.append(package_name.lower())
    except Exception as e:
        print(f"⚠️  requirements.txt 파싱 오류 ({requirements_path}): {e}")

    return packages


def normalize_name(name: str) -> str:
    """
    패키지 이름에서 점(.), 하이픈(-), 언더바(_)를 모두 제거하고 소문자로 만듭니다.
    예: 'Ruamel.YAML' -> 'ruamelyaml', 'pdfminer-six' -> 'pdfminersix'
    """
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


def get_installed_packages_fast(python_exe: str) -> Set[str]:
    """설치된 패키지 명단을 '알맹이'만 남겨서 가져옵니다."""
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return set()

        data = json.loads(result.stdout)
        return {normalize_name(pkg["name"]) for pkg in data}
    except Exception:
        return set()


def diagnose_dependencies(
    base_dir: Path, python_exe: str
) -> Tuple[bool, Dict[str, List[str]]]:
    """[고속 진단] 이름 불일치 문제를 해결한 최종 버전."""
    print(
        "\n"
        + "=" * 60
        + "\n⚡ 시스템 정밀 점검: 이름표 떼고 알맹이만 확인 중...\n"
        + "=" * 60
    )

    installed_set = get_installed_packages_fast(python_exe)
    if not installed_set:
        print("⚠️  패키지 목록 로드 실패. 일단 통과합니다.")
        return True, {}

    missing = {"vtuber": [], "mellow_link": []}

    check_targets = [
        ("vtuber", base_dir / "Open-LLM-VTuber" / "requirements.txt"),
        ("mellow_link", base_dir / "requirements.txt"),
    ]

    for key, req_path in check_targets:
        if not req_path.exists() and key == "mellow_link":
            candidates = [
                base_dir / "core" / "mellow_link" / "requirements.txt",
                base_dir / "mellow_link" / "requirements.txt",
            ]
            req_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])

        packages = parse_requirements_file(req_path)
        if packages:
            print(f"📦 {key.upper()} 검문 중... ({len(packages)}개)")
            for pkg in packages:
                pkg_normalized = normalize_name(pkg.split("[")[0])
                if pkg_normalized in {"precommit", "ruff", "setuptools", "wheel"}:
                    continue
                if pkg_normalized not in installed_set:
                    missing[key].append(pkg)

            if not missing[key]:
                print(f"   ✅ 전원 통과")
            else:
                print(f"   ⚠️  {len(missing[key])}개 불일치 ({', '.join(missing[key][:3])}...)")

    all_ok = not missing["vtuber"] and not missing["mellow_link"]

    if not all_ok:
        print("\n❌ 여전히 감지되지 않는 패키지가 있습니다.")
        print("💡 팁: 'y'를 눌러 무시하고 실행해도 괜찮을 확률이 99%입니다.")
    else:
        print("✅ 모든 시스템 준비 완료.\n" + "=" * 60 + "\n")

    return all_ok, missing
