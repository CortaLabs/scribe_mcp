from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ENTRY_RE = re.compile(
    r"^\[(?P<emoji>[^\]]+)\]\s+"
    r"\[(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+UTC)\]\s+"
    r"\[Agent:\s*(?P<agent>[^\]]*)\]\s+"
    r"\[Project:\s*(?P<project>[^\]]*)\]\s*"
    r"(?P<body>.*)$"
)

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*\s*=")


@dataclass
class Entry:
    index: int
    line_no: int
    emoji: str
    timestamp: str
    dt: Optional[datetime]
    agent: str
    project: str
    message: str
    meta: Dict[str, Any]
    raw: str

    def to_jsonable(self) -> Dict[str, Any]:
        data = asdict(self)
        data["dt"] = self.dt.isoformat() if self.dt else None
        return data


def parse_entry_time(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_filter_time(value: str, *, end_of_day: bool = False) -> datetime:
    text = value.strip()
    if text.endswith(" UTC"):
        parsed = parse_entry_time(text)
        if parsed:
            return parsed

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        d = datetime.strptime(text, "%Y-%m-%d").date()
        t = time.max if end_of_day else time.min
        return datetime.combine(d, t, tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid time {value!r}; use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS [UTC]"
        ) from exc


def smart_split(text: str, sep: str = ";", maxsplit: int = -1) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    escape = False
    depth = 0
    splits = 0

    for ch in text:
        if escape:
            buf.append(ch)
            escape = False
            continue

        if ch == "\\" and quote:
            buf.append(ch)
            escape = True
            continue

        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue

        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue

        if ch in "([{" :
            depth += 1
            buf.append(ch)
            continue

        if ch in ")]}" and depth > 0:
            depth -= 1
            buf.append(ch)
            continue

        if ch == sep and depth == 0 and (maxsplit < 0 or splits < maxsplit):
            parts.append("".join(buf).strip())
            buf = []
            splits += 1
            continue

        buf.append(ch)

    parts.append("".join(buf).strip())
    return parts


def looks_like_meta(text: str) -> bool:
    first = smart_split(text, ";", maxsplit=1)[0].strip()
    return bool(KEY_RE.match(first))


def split_body(body: str) -> Tuple[str, str]:
    if " | " not in body:
        return body.strip(), ""
    msg, tail = body.rsplit(" | ", 1)
    if looks_like_meta(tail):
        return msg.strip(), tail.strip()
    return body.strip(), ""


def parse_value(value: str) -> Any:
    s = value.strip()
    if s == "":
        return ""

    lowered = s.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("none", "null"):
        return None

    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?", s):
            return float(s)
    except ValueError:
        pass

    if (s[:1], s[-1:]) in (("[", "]"), ("{", "}"), ('"', '"'), ("'", "'")):
        try:
            return json.loads(s)
        except Exception:
            try:
                return ast.literal_eval(s)
            except Exception:
                return s

    return s


def parse_meta(meta_text: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    extras: List[str] = []

    if not meta_text.strip():
        return meta

    for part in smart_split(meta_text, ";"):
        if not part:
            continue
        if "=" not in part:
            extras.append(part)
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if not key:
            extras.append(part)
            continue
        meta[key] = parse_value(value)

    if extras:
        meta["_extra"] = extras
    return meta


def find_log_start(lines: Sequence[str]) -> Optional[int]:
    for i, line in enumerate(lines):
        if ENTRY_RE.match(line.rstrip("\n")):
            return i
    return None


def parse_lines(lines: Sequence[str]) -> List[Entry]:
    start = find_log_start(lines)
    if start is None:
        return []

    entries: List[Entry] = []
    current: Optional[Entry] = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            entries.append(current)
            current = None

    for zero_line_no, raw_line in enumerate(lines[start:], start=start):
        line = raw_line.rstrip("\n")
        match = ENTRY_RE.match(line)
        if match:
            flush()
            body = match.group("body") or ""
            message, meta_text = split_body(body)
            ts = match.group("timestamp").strip()
            current = Entry(
                index=len(entries),
                line_no=zero_line_no + 1,
                emoji=match.group("emoji").strip(),
                timestamp=ts,
                dt=parse_entry_time(ts),
                agent=match.group("agent").strip(),
                project=match.group("project").strip(),
                message=message,
                meta=parse_meta(meta_text),
                raw=line,
            )
            continue

        if current is not None and line.strip():
            current.raw += "\n" + line
            current.message += "\n" + line.strip()

    flush()
    for i, entry in enumerate(entries):
        entry.index = i
    return entries


def text_blob(entry: Entry) -> str:
    return "\n".join(
        [
            entry.emoji,
            entry.timestamp,
            entry.agent,
            entry.project,
            entry.message,
            json.dumps(entry.meta, ensure_ascii=False, sort_keys=True, default=str),
            entry.raw,
        ]
    )


def scalar_match(actual: Any, expected: str) -> bool:
    if expected == "*":
        return actual is not None

    expected_l = expected.lower()
    if isinstance(actual, list):
        return any(scalar_match(item, expected) for item in actual)
    if isinstance(actual, dict):
        return expected_l in json.dumps(actual, ensure_ascii=False, sort_keys=True, default=str).lower()
    if actual is None:
        return expected_l in ("none", "null")
    return str(actual).lower() == expected_l


def contains_match(actual: Any, needle: str) -> bool:
    needle_l = needle.lower()
    if isinstance(actual, list):
        return any(contains_match(item, needle) for item in actual)
    if isinstance(actual, dict):
        return needle_l in json.dumps(actual, ensure_ascii=False, sort_keys=True, default=str).lower()
    return needle_l in str(actual).lower()


def compile_meta_filters(items: Optional[Sequence[str]]) -> List[Tuple[str, str]]:
    filters: List[Tuple[str, str]] = []
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"--meta expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--meta key cannot be empty: {item!r}")
        filters.append((key, value.strip()))
    return filters


def entry_matches(
    entry: Entry,
    *,
    query: Optional[str] = None,
    regex: Optional[re.Pattern[str]] = None,
    agent: Optional[str] = None,
    project: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    meta_filters: Optional[Sequence[Tuple[str, str]]] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> bool:
    if agent and entry.agent.lower() != agent.lower():
        return False
    if project and entry.project.lower() != project.lower():
        return False
    if priority and not scalar_match(entry.meta.get("priority"), priority):
        return False
    if category and not scalar_match(entry.meta.get("category"), category):
        return False
    if tag and not contains_match(entry.meta.get("tags", []), tag):
        return False
    if since and (entry.dt is None or entry.dt < since):
        return False
    if until and (entry.dt is None or entry.dt > until):
        return False
    for key, expected in meta_filters or []:
        if not scalar_match(entry.meta.get(key), expected):
            return False
    if query and query.lower() not in text_blob(entry).lower():
        return False
    if regex and not regex.search(text_blob(entry)):
        return False
    return True


def search_entries(
    entries: Sequence[Entry],
    *,
    newest_first: bool = True,
    tail: Optional[int] = None,
    limit: Optional[int] = 20,
    **filters: Any,
) -> List[Entry]:
    scope: Sequence[Entry] = entries[-tail:] if tail and tail > 0 else entries
    iterable: Iterable[Entry] = reversed(scope) if newest_first else scope
    matches: List[Entry] = []
    for entry in iterable:
        if entry_matches(entry, **filters):
            matches.append(entry)
            if limit and limit > 0 and len(matches) >= limit:
                break
    return matches


def summarize(entries: Sequence[Entry]) -> Dict[str, Any]:
    def count(field: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in entries:
            value = getattr(e, field)
            out[value] = out.get(value, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    def count_meta(key: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in entries:
            value = e.meta.get(key)
            if isinstance(value, list):
                values = [str(v) for v in value]
            elif value is None:
                values = []
            else:
                values = [str(value)]
            for v in values:
                out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    dated = [e for e in entries if e.dt]
    return {
        "entries": len(entries),
        "first_timestamp": min((e.timestamp for e in dated), default=None),
        "last_timestamp": max((e.timestamp for e in dated), default=None),
        "agents": count("agent"),
        "projects": count("project"),
        "priorities": count_meta("priority"),
        "categories": count_meta("category"),
        "tags": count_meta("tags"),
    }


def shorten(text: str, width: int) -> str:
    text = " ".join(text.split())
    if width <= 0 or len(text) <= width:
        return text
    return text[: max(0, width - 1)].rstrip() + "…"


def render_entry(entry: Entry, *, show_meta: bool = True, width: int = 220) -> str:
    head = f"#{entry.index + 1} line {entry.line_no} {entry.emoji} [{entry.timestamp}] {entry.agent}/{entry.project}"
    body = shorten(entry.message, width)
    if show_meta and entry.meta:
        meta = json.dumps(entry.meta, ensure_ascii=False, sort_keys=True, default=str)
        return f"{head}\n  {body}\n  meta: {meta}"
    return f"{head}\n  {body}"


def run_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Parse and filter markdown progress logs.")
    parser.add_argument("file")
    parser.add_argument("-q", "--query")
    parser.add_argument("--regex")
    parser.add_argument("--agent")
    parser.add_argument("--project")
    parser.add_argument("--priority")
    parser.add_argument("--category")
    parser.add_argument("--tag")
    parser.add_argument("--meta", action="append")
    parser.add_argument("--since", type=lambda s: parse_filter_time(s))
    parser.add_argument("--until", type=lambda s: parse_filter_time(s, end_of_day=True))
    parser.add_argument("--tail", type=int)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--oldest-first", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ndjson", action="store_true")
    parser.add_argument("--no-meta", action="store_true")
    parser.add_argument("--width", type=int, default=220)
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--find-start", action="store_true")
    args = parser.parse_args(argv)

    if args.file == "-":
        raw_lines = sys.stdin.read().splitlines()
    else:
        with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
            raw_lines = handle.read().splitlines()

    entries = parse_lines(raw_lines)

    if args.find_start:
        start = find_log_start(raw_lines)
        print("" if start is None else start + 1)
        return 0 if start is not None else 1

    if not entries:
        print("No progress-log entries found.", file=sys.stderr)
        return 1

    if args.stats:
        print(json.dumps(summarize(entries), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    regex = None
    if args.regex:
        try:
            regex = re.compile(args.regex, re.IGNORECASE | re.MULTILINE)
        except re.error as exc:
            print(f"Invalid --regex: {exc}", file=sys.stderr)
            return 2

    matches = search_entries(
        entries,
        newest_first=not args.oldest_first,
        tail=args.tail,
        limit=args.limit,
        query=args.query,
        regex=regex,
        agent=args.agent,
        project=args.project,
        priority=args.priority,
        category=args.category,
        tag=args.tag,
        meta_filters=compile_meta_filters(args.meta),
        since=args.since,
        until=args.until,
    )

    if args.json:
        print(json.dumps([entry.to_jsonable() for entry in matches], ensure_ascii=False, indent=2, sort_keys=True))
    elif args.ndjson:
        for entry in matches:
            print(json.dumps(entry.to_jsonable(), ensure_ascii=False, sort_keys=True))
    else:
        for i, entry in enumerate(matches):
            if i:
                print()
            print(render_entry(entry, show_meta=not args.no_meta, width=args.width))

    return 0


__all__ = [
    "Entry",
    "ENTRY_RE",
    "compile_meta_filters",
    "contains_match",
    "entry_matches",
    "find_log_start",
    "parse_entry_time",
    "parse_filter_time",
    "parse_lines",
    "parse_meta",
    "parse_value",
    "render_entry",
    "run_cli",
    "search_entries",
    "shorten",
    "smart_split",
    "split_body",
    "summarize",
    "text_blob",
]
