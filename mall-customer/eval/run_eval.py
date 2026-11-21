"""RAG 检索质量评测 — 离线跑向量索引，不经过 LLM。

只评「检索层」：Query 改写与生成都不参与，指标因此可复现、可对比。

指标：
- hit@3     ：知识库确有答案的问题，前 3 条召回里是否命中预期文档
- 空召回准确率：知识库没有依据的问题，检索是否如实返回空

用法（在 mall-customer 目录下）：
    python -m eval.run_eval
    python -m eval.run_eval --top-k 5 --verbose

前提：`.env` 里配好 OPENAI_API_KEY / OPENAI_BASE_URL / EMBEDDING_MODEL，
向量索引已由 knowledge_base/ 构建（缺失时会自动重建一次）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

# Windows 控制台默认 GBK，中文与 ✓ / ✗ 会直接抛 UnicodeEncodeError
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from memory.long_term_memory import LongTermMemory  # noqa: E402

CASES_PATH = Path(__file__).with_name("cases.json")
KNOWLEDGE_BASE_DIR = os.getenv("KNOWLEDGE_BASE_DIR", "./knowledge_base")
INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.5"))


@dataclass
class CaseResult:
    query: str
    expected: str | None
    retrieved: list[str]
    scores: list[float]
    hit: bool | None = None
    empty_recall: bool = False
    note: str = ""


@dataclass
class Report:
    total: int = 0
    answerable: int = 0
    negative: int = 0
    hits: int = 0
    empty_correct: int = 0
    misses: list[CaseResult] = field(default_factory=list)
    false_positives: list[CaseResult] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.answerable if self.answerable else 0.0

    @property
    def empty_accuracy(self) -> float:
        return self.empty_correct / self.negative if self.negative else 0.0


def load_cases(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def build_memory() -> LongTermMemory:
    """加载已落盘索引；没有索引时从知识库重建（首次运行会调 embedding 接口）。"""
    memory = LongTermMemory(index_path=INDEX_PATH, min_score=RAG_MIN_SCORE)
    if memory.document_count == 0:
        kb_dir = BASE_DIR / KNOWLEDGE_BASE_DIR.lstrip("./")
        loaded = memory.load_knowledge_base(str(kb_dir))
        print(f"[初始化] 知识库为空，已从 {kb_dir} 导入 {loaded} 篇文档并落盘")
        if loaded == 0:
            raise SystemExit(f"知识库导入失败：{kb_dir} 下没有可用的 .md 文件")
    return memory


def evaluate(memory: LongTermMemory, cases: list[dict], top_k: int, verbose: bool) -> Report:
    report = Report(total=len(cases))
    for case in cases:
        query = case["query"]
        expected = case.get("expected")
        results = memory.search(query, top_k=top_k)
        sources = [_stem(doc) for doc in results]
        scores = [round(float(doc.get("score", 0.0)), 4) for doc in results]

        result = CaseResult(
            query=query,
            expected=expected,
            retrieved=sources,
            scores=scores,
            note=case.get("note", ""),
        )

        if expected is None:
            report.negative += 1
            result.empty_recall = len(sources) == 0
            if result.empty_recall:
                report.empty_correct += 1
            else:
                report.false_positives.append(result)
        else:
            report.answerable += 1
            result.hit = expected in sources
            if result.hit:
                report.hits += 1
            else:
                report.misses.append(result)

        if verbose:
            mark = "✓" if (result.hit or result.empty_recall) else "✗"
            print(f"{mark} {query}")
            print(f"    期望: {expected or '(空召回)'}")
            print(f"    实得: {list(zip(sources, scores)) or '(空)'}")

    return report


def _stem(doc: dict) -> str:
    """把文档来源统一成知识库文件名（不含扩展名），与 cases.json 的 expected 对齐。"""
    source = doc.get("source") or (doc.get("metadata") or {}).get("file") or ""
    return Path(str(source)).stem


def print_report(report: Report, top_k: int) -> None:
    print()
    print("=" * 60)
    print("RAG 检索评测结果")
    print("=" * 60)
    print(f"用例总数        : {report.total}")
    print(f"可回答用例      : {report.answerable}")
    print(f"hit@{top_k}         : {report.hits}/{report.answerable} = {report.hit_rate:.1%}")
    print(f"负样本用例      : {report.negative}")
    print(f"空召回准确率    : {report.empty_correct}/{report.negative} = {report.empty_accuracy:.1%}")

    if report.misses:
        print()
        print(f"未命中 {len(report.misses)} 条：")
        for item in report.misses:
            print(f"  - {item.query}")
            print(f"    期望 {item.expected}，实得 {item.retrieved or '(空)'} {item.scores}")

    if report.false_positives:
        print()
        print(f"负样本误召回 {len(report.false_positives)} 条：")
        for item in report.false_positives:
            print(f"  - {item.query}")
            print(f"    误召 {item.retrieved} {item.scores}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 检索质量评测")
    parser.add_argument("--top-k", type=int, default=3, help="每个问题取前 k 条召回，默认 3")
    parser.add_argument("--verbose", action="store_true", help="逐条打印召回结果")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="评测集路径")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    memory = build_memory()
    print(f"[就绪] 知识库 {memory.document_count} 篇，阈值 {RAG_MIN_SCORE}，用例 {len(cases)} 条")

    report = evaluate(memory, cases, top_k=args.top_k, verbose=args.verbose)
    print_report(report, args.top_k)

    if report.hit_rate < 0.7 or report.empty_accuracy < 0.7:
        print("\n结果低于 70% 基线，请检查切分方式或知识缺口，不要靠改文档凑分。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
