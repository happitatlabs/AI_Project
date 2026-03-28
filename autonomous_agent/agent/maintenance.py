"""
maintenance.py — Maintenance Layer

역할:
- 로그 롤링: agent.log → logs/agent_YYYYMMDD.log
- 오래된 로그 삭제(또는 gzip 압축)
- generated_skills/ 오래된 파일 → archive/ 이동
- 중복 스킬 파일 탐지 및 제거 (MD5 해시 기반)
- agent_memory.json 히스토리 제한 및 요약 (초과분 archive)

독립 실행 가능: python run_maintenance.py
기존 구조 무수정: memory/planner/executor를 직접 호출하지 않음
"""

import gzip
import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("maintenance")


class MaintenanceRunner:
    """
    모든 유지보수 작업을 담당하는 클래스.

    독립적으로 각 메서드를 호출하거나,
    run_all()로 전체 작업을 순서대로 실행할 수 있다.
    """

    def __init__(self, config: dict, base_dir: str = "."):
        self.base_dir = base_dir
        mcfg = config.get("maintenance", {})
        lcfg = config.get("logging", {})

        self.log_dir         = os.path.join(base_dir, mcfg.get("log_dir",    "logs"))
        self.archive_dir     = os.path.join(base_dir, mcfg.get("archive_dir","archive"))
        self.skills_dir      = os.path.join(base_dir, "generated_skills")
        self.memory_file     = os.path.join(
            base_dir, config.get("agent", {}).get("memory_file", "agent_memory.json")
        )
        self.log_file        = os.path.join(
            base_dir, lcfg.get("log_file", "agent.log")
        )

        self.log_retention_days   = mcfg.get("log_retention_days",   7)
        self.skills_archive_days  = mcfg.get("skills_archive_days",  30)
        self.memory_max_history   = mcfg.get("memory_max_history",   100)
        self.compress_old_logs    = mcfg.get("compress_old_logs",    True)

        os.makedirs(self.log_dir,     exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
        os.makedirs(self.skills_dir,  exist_ok=True)

    # ══════════════════════════════════════════════════
    # 공개 API
    # ══════════════════════════════════════════════════

    def run_all(self) -> dict[str, Any]:
        """모든 유지보수 작업을 순서대로 실행하고 결과를 반환."""
        print("\n[Maintenance] ── 유지보수 시작 ──")
        results = {}
        tasks = [
            ("log_rolling",       self.roll_logs),
            ("log_cleanup",       self.cleanup_old_logs),
            ("skills_archive",    self.archive_old_skills),
            ("skills_dedup",      self.deduplicate_skills),
            ("memory_trim",       self.trim_memory),
        ]
        for name, fn in tasks:
            try:
                results[name] = fn()
                print(f"  ✅ {name}: {results[name]}")
            except Exception as e:
                results[name] = {"error": str(e)}
                logger.error(f"[Maintenance] {name} 실패: {e}")
                print(f"  ❌ {name}: {e}")

        print("[Maintenance] ── 완료 ──\n")
        return results

    # ══════════════════════════════════════════════════
    # 1. 로그 롤링
    # ══════════════════════════════════════════════════

    def roll_logs(self) -> dict:
        """
        agent.log를 오늘 날짜 파일로 이동하고 새 빈 로그 생성.
        logs/agent_YYYYMMDD.log
        """
        if not os.path.exists(self.log_file):
            return {"action": "skipped", "reason": "log_file not found"}
        if os.path.getsize(self.log_file) == 0:
            return {"action": "skipped", "reason": "log_file is empty"}

        today    = datetime.now().strftime("%Y%m%d")
        dest     = os.path.join(self.log_dir, f"agent_{today}.log")

        # 같은 날짜 파일이 있으면 append
        if os.path.exists(dest):
            with open(self.log_file, "r", encoding="utf-8", errors="replace") as src_f:
                content = src_f.read()
            with open(dest, "a", encoding="utf-8") as dst_f:
                dst_f.write(content)
            action = "appended"
        else:
            shutil.move(self.log_file, dest)
            action = "moved"

        # 새 빈 로그 파일 생성
        open(self.log_file, "w").close()
        size = os.path.getsize(dest)
        logger.info(f"[Maintenance] 로그 롤링: {dest} ({size:,} bytes)")
        return {"action": action, "dest": dest, "size_bytes": size}

    # ══════════════════════════════════════════════════
    # 2. 오래된 로그 정리
    # ══════════════════════════════════════════════════

    def cleanup_old_logs(self) -> dict:
        """
        retention 기간 초과 로그를 gzip 압축 또는 삭제.
        """
        cutoff   = datetime.now() - timedelta(days=self.log_retention_days)
        removed  = []
        compressed = []

        for fname in os.listdir(self.log_dir):
            if not fname.endswith(".log"):
                continue
            fpath = os.path.join(self.log_dir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))

            if mtime >= cutoff:
                continue

            if self.compress_old_logs:
                gz_path = fpath + ".gz"
                with open(fpath, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(fpath)
                compressed.append(fname)
                logger.info(f"[Maintenance] 압축: {fname} → {fname}.gz")
            else:
                os.remove(fpath)
                removed.append(fname)
                logger.info(f"[Maintenance] 삭제: {fname}")

        # 이미 압축된 .gz 파일도 retention 기간 2배 초과 시 삭제
        cutoff_gz = datetime.now() - timedelta(days=self.log_retention_days * 2)
        for fname in os.listdir(self.log_dir):
            if not fname.endswith(".gz"):
                continue
            fpath = os.path.join(self.log_dir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff_gz:
                os.remove(fpath)
                removed.append(fname)
                logger.info(f"[Maintenance] 압축 파일 삭제: {fname}")

        return {
            "compressed": compressed,
            "removed": removed,
            "cutoff_days": self.log_retention_days,
        }

    # ══════════════════════════════════════════════════
    # 3. 오래된 스킬 파일 아카이브
    # ══════════════════════════════════════════════════

    def archive_old_skills(self) -> dict:
        """
        skills_archive_days 초과 스킬 파일을 archive/skills/ 로 이동.
        """
        archive_skills_dir = os.path.join(self.archive_dir, "skills")
        os.makedirs(archive_skills_dir, exist_ok=True)

        cutoff  = datetime.now() - timedelta(days=self.skills_archive_days)
        moved   = []

        for fname in os.listdir(self.skills_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(self.skills_dir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                dest = os.path.join(archive_skills_dir, fname)
                # 이름 충돌 방지
                if os.path.exists(dest):
                    stem, ext = os.path.splitext(fname)
                    dest = os.path.join(
                        archive_skills_dir,
                        f"{stem}_{int(mtime.timestamp())}{ext}"
                    )
                shutil.move(fpath, dest)
                moved.append(fname)
                logger.info(f"[Maintenance] 스킬 아카이브: {fname}")

        return {"archived": moved, "cutoff_days": self.skills_archive_days}

    # ══════════════════════════════════════════════════
    # 4. 중복 스킬 제거
    # ══════════════════════════════════════════════════

    def deduplicate_skills(self) -> dict:
        """
        generated_skills/ 내 파일 내용의 MD5 해시를 비교해 중복 제거.
        가장 최신 파일을 남기고 나머지를 archive/skills/duplicates/ 로 이동.
        """
        dup_dir = os.path.join(self.archive_dir, "skills", "duplicates")
        os.makedirs(dup_dir, exist_ok=True)

        hash_map: dict[str, str] = {}  # hash → newest_filepath
        duplicates = []

        files = sorted(
            [f for f in os.listdir(self.skills_dir) if f.endswith(".md")],
            key=lambda f: os.path.getmtime(os.path.join(self.skills_dir, f)),
            reverse=True,  # 최신 파일 우선
        )

        for fname in files:
            fpath = os.path.join(self.skills_dir, fname)
            content_hash = self._file_hash(fpath)
            if content_hash in hash_map:
                dest = os.path.join(dup_dir, fname)
                shutil.move(fpath, dest)
                duplicates.append(fname)
                logger.info(f"[Maintenance] 중복 스킬 이동: {fname}")
            else:
                hash_map[content_hash] = fpath

        return {"duplicates_removed": duplicates, "unique_kept": len(hash_map)}

    # ══════════════════════════════════════════════════
    # 5. 메모리 히스토리 트리밍
    # ══════════════════════════════════════════════════

    def trim_memory(self) -> dict:
        """
        agent_memory.json의 history가 memory_max_history를 초과하면
        오래된 항목을 archive/memory_overflow_YYYYMMDD.jsonl 로 이동 후 요약 추가.
        """
        if not os.path.exists(self.memory_file):
            return {"action": "skipped", "reason": "memory_file not found"}

        with open(self.memory_file, "r", encoding="utf-8") as f:
            memory = json.load(f)

        history = memory.get("history", [])
        total   = len(history)

        if total <= self.memory_max_history:
            return {"action": "skipped", "total": total, "limit": self.memory_max_history}

        # 초과분 분리
        keep_from     = total - self.memory_max_history
        overflow      = history[:keep_from]
        kept          = history[keep_from:]

        # 초과분 → archive
        archive_dir_mem = os.path.join(self.archive_dir, "memory")
        os.makedirs(archive_dir_mem, exist_ok=True)
        today      = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_path  = os.path.join(archive_dir_mem, f"memory_overflow_{today}.jsonl")
        with open(dump_path, "w", encoding="utf-8") as f:
            for entry in overflow:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 요약 항목 생성 (초과분 대표 통계)
        scores = [
            e.get("evaluation", {}).get("score", 0)
            for e in overflow if "evaluation" in e
        ]
        summary_entry = {
            "cycle": f"summary_{overflow[0].get('cycle','?')}-{overflow[-1].get('cycle','?')}",
            "type": "maintenance_summary",
            "trimmed_count": len(overflow),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "archive_file": dump_path,
            "trimmed_at": datetime.now().isoformat(),
        }

        memory["history"] = [summary_entry] + kept
        memory["metadata"]["last_updated"] = datetime.now().isoformat()

        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[Maintenance] 메모리 트리밍: {total} → {len(kept)+1} "
            f"(초과 {len(overflow)}개 → {dump_path})"
        )
        return {
            "action": "trimmed",
            "before": total,
            "after": len(kept) + 1,
            "archived": len(overflow),
            "archive_file": dump_path,
        }

    # ══════════════════════════════════════════════════
    # 유틸리티
    # ══════════════════════════════════════════════════

    @staticmethod
    def _file_hash(path: str) -> str:
        """파일 내용의 MD5 해시를 반환."""
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
