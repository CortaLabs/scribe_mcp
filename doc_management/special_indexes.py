"""Index and template helpers for special document workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scribe_mcp.doc_management import preflight as preflight_shared
from scribe_mcp.doc_management.manager import DocumentOperationError


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _write_file_atomically(file_path: Path, content: str) -> bool:
    return preflight_shared.write_file_atomically(file_path, content)


def _validate_and_repair_index(index_path: Path, doc_dir: Path) -> bool:
    return preflight_shared.validate_and_repair_index(index_path, doc_dir)


async def update_research_index(research_dir: Path, agent_id: str) -> None:
    index_path = research_dir / "INDEX.md"

    if not _validate_and_repair_index(index_path, research_dir):
        import logging

        logging.getLogger(__name__).debug("Auto-repairing research index for %s", research_dir.name)

    research_docs = []
    if research_dir.exists():
        for doc_path in research_dir.glob("*.md"):
            if doc_path.name != "INDEX.md" and not doc_path.name.startswith("_"):
                stat = doc_path.stat()
                research_docs.append(
                    {
                        "name": doc_path.stem,
                        "path": doc_path.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )

    content = f"""# Research Documents Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains research documents generated during the development process.

## Available Research Documents

"""

    if research_docs:
        research_docs.sort(key=lambda x: x["modified"], reverse=True)
        for doc in research_docs:
            modified_time = datetime.fromtimestamp(doc["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{doc['name']}]({doc['path']})** - {modified_time} ({doc['size']} bytes)\n"
    else:
        content += "*No research documents found.*\n"

    content += f"""

## Index Information

- **Total Documents:** {len(research_docs)}
- **Index Location:** `{index_path.relative_to(research_dir.parent.parent)}`

---

*This index is automatically updated when research documents are created or modified.*"""

    if not _write_file_atomically(index_path, content):
        import logging

        logging.getLogger(__name__).warning("Failed to update research index at %s", index_path)


async def update_bug_index(bugs_dir: Path, agent_id: str) -> None:
    index_path = bugs_dir / "INDEX.md"

    bug_reports = []
    if bugs_dir.exists():
        for category_dir in bugs_dir.iterdir():
            if category_dir.is_dir() and category_dir.name != "archived":
                for bug_dir in category_dir.iterdir():
                    if bug_dir.is_dir():
                        report_path = bug_dir / "report.md"
                        if report_path.exists():
                            stat = report_path.stat()
                            bug_reports.append(
                                {
                                    "category": category_dir.name,
                                    "slug": bug_dir.name,
                                    "path": str(report_path.relative_to(bugs_dir)),
                                    "size": stat.st_size,
                                    "modified": stat.st_mtime,
                                }
                            )

    content = f"""# Bug Reports Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains bug reports generated during development and testing.

## Bug Statistics

- **Total Reports:** {len(bug_reports)}
- **Categories:** {len(set(report['category'] for report in bug_reports))}

## Recent Bug Reports

"""

    if bug_reports:
        bug_reports.sort(key=lambda x: x["modified"], reverse=True)
        for bug in bug_reports[:20]:
            modified_time = datetime.fromtimestamp(bug["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{bug['category']}/{bug['slug']}]({bug['path']})** - {modified_time}\n"
        if len(bug_reports) > 20:
            content += f"\n*... and {len(bug_reports) - 20} older reports*\n"
    else:
        content += "*No bug reports found.*\n"

    content += "\n## Browse by Category\n\n"

    categories: Dict[str, list] = {}
    for bug in bug_reports:
        categories.setdefault(bug["category"], []).append(bug)

    for category, bugs in sorted(categories.items()):
        content += f"### {category.title()} ({len(bugs)} reports)\n"
        for bug in bugs[:5]:
            content += f"- [{bug['slug']}]({bug['path']})\n"
        if len(bugs) > 5:
            content += f"- ... and {len(bugs) - 5} more\n"
        content += "\n"

    content += f"""---

## Index Information

- **Index Location:** `{index_path}`
- **Total Categories:** {len(categories)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when bug reports are created or modified.*"""

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(content)


async def update_review_index(docs_dir: Path, agent_id: str) -> None:
    index_path = docs_dir / "REVIEW_INDEX.md"

    review_reports = []
    for review_file in docs_dir.glob("REVIEW_REPORT_*.md"):
        if review_file.name != "REVIEW_INDEX.md":
            stat = review_file.stat()
            parts = review_file.stem.split("_")
            stage = parts[2] if len(parts) > 2 else "unknown"
            review_reports.append(
                {
                    "name": review_file.stem,
                    "path": review_file.name,
                    "stage": stage,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                }
            )

    content = f"""# Review Reports Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains review reports generated during the development quality assurance process.

## Review Statistics

- **Total Reports:** {len(review_reports)}
- **Stages Reviewed:** {len(set(report['stage'] for report in review_reports))}

## Recent Review Reports

"""

    if review_reports:
        review_reports.sort(key=lambda x: x["modified"], reverse=True)
        for report in review_reports[:20]:
            modified_time = datetime.fromtimestamp(report["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{report['name']}]({report['path']})** - {report['stage']} - {modified_time}\n"
        if len(review_reports) > 20:
            content += f"\n*... and {len(review_reports) - 20} older reports*\n"
    else:
        content += "*No review reports found.*\n"

    content += "\n## Browse by Stage\n\n"

    stages: Dict[str, list] = {}
    for report in review_reports:
        stages.setdefault(report["stage"], []).append(report)

    for stage, reports in sorted(stages.items()):
        content += f"### {stage.title()} ({len(reports)} reports)\n"
        for report in reports[:5]:
            content += f"- [{report['name']}]({report['path']})\n"
        if len(reports) > 5:
            content += f"- ... and {len(reports) - 5} more\n"
        content += "\n"

    content += f"""

## Index Information

- **Index Location:** `{index_path}`
- **Total Stages:** {len(stages)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when review reports are created or modified.*"""

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(content)


async def update_agent_card_index(docs_dir: Path, agent_id: str) -> None:
    index_path = docs_dir / "AGENT_CARDS_INDEX.md"

    agent_cards = []
    for card_file in docs_dir.glob("AGENT_REPORT_CARD_*.md"):
        if card_file.name != "AGENT_CARDS_INDEX.md":
            stat = card_file.stat()
            parts = card_file.stem.split("_")
            agent_name = parts[3] if len(parts) > 3 else "unknown"
            stage = parts[4] if len(parts) > 4 else "unknown"
            agent_cards.append(
                {
                    "name": card_file.stem,
                    "path": card_file.name,
                    "agent": agent_name,
                    "stage": stage,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                }
            )

    content = f"""# Agent Report Cards Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains agent performance evaluation reports generated during the development process.

## Agent Statistics

- **Total Reports:** {len(agent_cards)}
- **Agents Evaluated:** {len(set(report['agent'] for report in agent_cards))}
- **Stages Covered:** {len(set(report['stage'] for report in agent_cards))}

## Recent Agent Evaluations

"""

    if agent_cards:
        agent_cards.sort(key=lambda x: x["modified"], reverse=True)
        for card in agent_cards[:20]:
            modified_time = datetime.fromtimestamp(card["modified"]).strftime("%Y-%m-%d %H:%M")
            content += (
                f"- **[{card['name']}]({card['path']})** - "
                f"{card['agent']} - {card['stage']} - {modified_time}\n"
            )
        if len(agent_cards) > 20:
            content += f"\n*... and {len(agent_cards) - 20} older evaluations*\n"
    else:
        content += "*No agent report cards found.*\n"

    content += "\n## Browse by Agent\n\n"

    agents: Dict[str, list] = {}
    for card in agent_cards:
        agents.setdefault(card["agent"], []).append(card)

    for agent, cards in sorted(agents.items()):
        content += f"### {agent} ({len(cards)} evaluations)\n"
        for card in cards[:5]:
            content += f"- [{card['name']}]({card['path']})\n"
        if len(cards) > 5:
            content += f"- ... and {len(cards) - 5} more\n"
        content += "\n"

    content += f"""

## Index Information

- **Index Location:** `{index_path}`
- **Total Agents:** {len(agents)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when agent report cards are created or modified.*"""

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(content)


async def render_review_report_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
    logger: Any,
) -> str:
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox",
        )

        template_context = prepared_metadata.copy()
        template_context.setdefault("project_name", project.get("name", ""))
        template_context.setdefault("agent_id", agent_id)
        template_context.setdefault("timestamp", _current_timestamp())
        template_context.setdefault("stage", prepared_metadata.get("stage", "unknown"))

        return engine.render_template(
            template_name="REVIEW_REPORT_TEMPLATE.md",
            metadata=template_context,
        )
    except (TemplateEngineError, ImportError) as exc:
        logger.warning("Template engine error for review report: %s", exc)
        stage = prepared_metadata.get("stage", "unknown")
        overall_decision = prepared_metadata.get("overall_decision", "[PENDING]")
        final_decision = prepared_metadata.get("final_decision", overall_decision)
        return f"""# Review Report: {stage.replace('_', ' ').title()} Stage

**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Decision:** {overall_decision}

---

<!-- ID: final_decision -->
## Final Decision

**{final_decision}**

*This review report is part of the quality assurance process for {project.get('name')}.*"""
    except Exception as exc:
        logger.error("Unexpected error rendering review report template: %s", exc)
        raise DocumentOperationError(f"Failed to render review report template: {exc}") from exc


async def render_agent_report_card_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
    logger: Any,
) -> str:
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox",
        )

        template_context = prepared_metadata.copy()
        template_context.setdefault("project_name", project.get("name", ""))
        template_context.setdefault("agent_id", agent_id)
        template_context.setdefault("timestamp", _current_timestamp())
        template_context.setdefault("agent_name", prepared_metadata.get("agent_name", agent_id))
        template_context.setdefault("stage", prepared_metadata.get("stage", "unknown"))

        return engine.render_template(
            template_name="AGENT_REPORT_CARD_TEMPLATE.md",
            metadata=template_context,
        )
    except (TemplateEngineError, ImportError) as exc:
        logger.warning("Template engine error for agent report card: %s", exc)
        agent_name = prepared_metadata.get("agent_name", agent_id)
        stage = prepared_metadata.get("stage", "unknown")
        overall_grade = prepared_metadata.get("overall_grade", "[PENDING]")
        final_recommendation = prepared_metadata.get("final_recommendation", "[PENDING]")
        return f"""# Agent Performance Report Card

**Agent:** {agent_name}
**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Grade:** {overall_grade}

---

<!-- ID: final_assessment -->
## Final Assessment

**Overall Recommendation:** {final_recommendation}

*This agent report card is part of the performance management system for {project.get('name')}.*"""
    except Exception as exc:
        logger.error("Unexpected error rendering agent report card template: %s", exc)
        raise DocumentOperationError(f"Failed to render agent report card template: {exc}") from exc
