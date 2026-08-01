"""Obsidian Vault integration for markdown notes and frontmatter metadata."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class ObsidianNote:
    """Representation of an Obsidian markdown note."""

    title: str
    path: Path
    content: str
    frontmatter: dict[str, Any] = field(default_factory=dict)


class ObsidianVaultManager:
    """Direct file-system interface for managing an Obsidian Vault."""

    def __init__(self, vault_path: Optional[str | Path] = None):
        if not vault_path:
            raise ValueError(
                "Obsidian Vault path is missing. " \
                "Set OBSIDIAN_VAULT_PATH in your .env file."
            )
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise FileNotFoundError(f"Obsidian Vault path does not exist: " \
                                    f"{self.vault_path}")

    # -------------------------------------------------------------------------
    # Helper Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def _format_frontmatter(metadata: dict[str, Any]) -> str:
        """Format a dictionary into YAML frontmatter string."""
        if not metadata:
            return ""
        lines = ["---"]
        for key, value in metadata.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---\n")
        return "\n".join(lines)

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
        """Extract YAML frontmatter dictionary and main body content from note."""
        frontmatter = {}
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_str = parts[1]
                body = parts[2].lstrip()
                # Basic line-by-line key-value parsing for standard scalar fields
                for line in yaml_str.strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        frontmatter[k.strip()] = v.strip()

        return frontmatter, body

    # -------------------------------------------------------------------------
    # Daily Notes Management
    # -------------------------------------------------------------------------

    def get_daily_note_path(
        self,
        date_obj: Optional[date] = None,
        folder_name: str = "Daily Notes",
    ) -> Path:
        """Get the file path for a daily note (formatted as YYYY-MM-DD.md)."""
        target_date = date_obj or date.today()
        daily_folder = self.vault_path / folder_name
        daily_folder.mkdir(parents=True, exist_ok=True)
        return daily_folder / f"{target_date.strftime('%Y-%m-%d')}.md"

    def append_to_daily_note(
        self,
        content: str,
        section_heading: Optional[str] = None,
        date_obj: Optional[date] = None,
        folder_name: str = "Daily Notes",
    ) -> Path:
        """
        Append text or markdown sections to today's daily note.
        Creates the daily note if it does not exist yet.
        """
        note_path = self.get_daily_note_path(date_obj=date_obj, folder_name=folder_name)
        target_date = date_obj or date.today()

        if not note_path.exists():
            # Create fresh daily note template
            initial_frontmatter = self._format_frontmatter(
                {
                    "created": target_date.strftime("%Y-%m-%d"),
                    "tags": ["daily-note", "lifeos"],
                }
            )
            header = f"# Daily Log - {target_date.strftime('%A, %B %d, %Y')}\n\n"
            note_path.write_text(initial_frontmatter + header, encoding="utf-8")

        # existing_content = note_path.read_text(encoding="utf-8")

        with open(note_path, "a", encoding="utf-8") as f:
            if section_heading:
                f.write(f"\n\n## {section_heading}\n")
            else:
                f.write("\n\n")
            f.write(content.strip())

        return note_path

    # -------------------------------------------------------------------------
    # Project & Academic Notes
    # -------------------------------------------------------------------------

    def create_or_update_note(
        self,
        relative_path: str,
        title: str,
        body: str,
        frontmatter: Optional[dict[str, Any]] = None,
    ) -> Path:
        """Create or replace a project/research note in the vault."""
        note_path = (self.vault_path / relative_path).resolve()
        note_path.parent.mkdir(parents=True, exist_ok=True)

        meta = frontmatter or {}
        meta.setdefault("updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
        meta.setdefault("tags", ["lifeos"])

        full_text = self._format_frontmatter(meta)
        full_text += f"# {title}\n\n" + body.strip() + "\n"

        note_path.write_text(full_text, encoding="utf-8")
        return note_path

    def read_note(self, relative_path: str) -> Optional[ObsidianNote]:
        """Read a note from relative path inside the vault."""
        note_path = (self.vault_path / relative_path).resolve()
        if not note_path.exists():
            return None

        content = note_path.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(content)
        title = note_path.stem

        # Extract title from first H1 header if present
        h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()

        return ObsidianNote(
            title=title,
            path=note_path,
            content=body,
            frontmatter=frontmatter,
        )
