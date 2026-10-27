"""Maintenance checks only; these do not execute the Agent Flow workflow."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SKILLS = {"flow-explore", "flow-plan", "flow-execute", "flow-verify"}
DOCS = {"context.md", "documents.md", "execution.md", "verification.md", "extensions.md"}
TEMPLATES = {
    "workspace.md", "repository.md", "work.md", "investigation.md",
    "requirements.md", "design.md", "plan.md", "verification.md",
}
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^\s)]+)\)")


def markdown_files():
    folders = [ROOT / "docs", ROOT / "templates", ROOT / "tests", ROOT / ".agents"]
    return sorted({*ROOT.glob("*.md"), *(p for folder in folders for p in folder.rglob("*.md"))})


def prose_lines(text):
    """Inspect the repository's inline-link style, ignoring fenced examples."""
    marker, minimum = None, 0
    for number, line in enumerate(text.splitlines(), 1):
        fence = FENCE.match(line)
        if fence:
            run, suffix = fence.groups()
            if marker is None:
                marker, minimum = run[0], len(run)
            elif run[0] == marker and len(run) >= minimum and not suffix.strip():
                marker = None
            continue
        if marker is None:
            yield number, re.sub(r"`[^`]*`", "", line)
    if marker is not None:
        raise ValueError("Unclosed fenced block")


class ProjectChecks(unittest.TestCase):
    def test_fenced_examples_are_not_link_targets(self):
        sample = "[real](docs/context.md)\n```text\n[example](missing.md)\n```\n"
        self.assertEqual([(1, "[real](docs/context.md)")], list(prose_lines(sample)))
        with self.assertRaises(ValueError):
            list(prose_lines("```text\nunclosed\n"))

    def test_inline_command_examples_are_not_link_targets(self):
        sample = "Run `[example](missing.md)`; read [real](docs/context.md).\n"
        lines = list(prose_lines(sample))
        self.assertEqual(["docs/context.md"], LINK.findall(lines[0][1]))

    def test_exactly_four_core_skills(self):
        actual = {p.name for p in (ROOT / ".agents/skills").iterdir() if p.is_dir()}
        self.assertEqual(SKILLS, actual)
        for name in actual:
            self.assertTrue((ROOT / ".agents/skills" / name / "SKILL.md").is_file())

    def test_skill_metadata(self):
        skills = [*(ROOT / ".agents/skills").glob("*/SKILL.md"),
                  ROOT / "docs/examples/local-evidence/SKILL.md"]
        for path in skills:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
                self.assertIsNotNone(match, "Missing frontmatter")
                # This project intentionally uses only two one-line plain scalars.
                fields = {}
                for line in match.group(1).splitlines():
                    key, separator, value = line.partition(":")
                    self.assertTrue(separator and key and value.strip(), line)
                    self.assertNotIn(key, fields)
                    fields[key] = value.strip()
                self.assertEqual({"name", "description"}, set(fields))
                self.assertEqual(path.parent.name, fields["name"])
                self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertLessEqual(len(fields["name"]), 64)
                self.assertLessEqual(len(fields["description"]), 1024)
                self.assertNotIn(": ", fields["description"])
                self.assertNotIn("<", fields["description"])
                self.assertNotIn(">", fields["description"])
                self.assertTrue(text[match.end():].strip())

    def test_shared_docs_and_optional_templates(self):
        self.assertEqual(DOCS, {p.name for p in (ROOT / "docs").glob("*.md")})
        self.assertEqual(TEMPLATES | {"README.md"},
                         {p.name for p in (ROOT / "templates").glob("*.md")})
        self.assertEqual({"delegation.md", "task-result.md"},
                         {p.name for p in (ROOT / "templates/fragments").glob("*.md")})
        for path in (ROOT / "templates").rglob("*.md"):
            if path.name != "README.md":
                self.assertTrue(any(line.startswith("> ") for line in path.read_text().splitlines()), path)

    def test_local_inline_links(self):
        checked = 0
        for path in markdown_files():
            for number, line in prose_lines(path.read_text(encoding="utf-8")):
                for raw in LINK.findall(line):
                    parsed = urlsplit(raw)
                    if parsed.scheme or parsed.netloc:
                        self.assertIn(parsed.scheme, {"https", "http", "mailto"}, raw)
                        continue  # Maintenance checks never follow remote URLs.
                    target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
                    with self.subTest(path=path.relative_to(ROOT), line=number, target=raw):
                        self.assertTrue(target.is_relative_to(ROOT), "Link escapes the project")
                        self.assertTrue(target.exists(), "Missing local link target")
                    checked += 1
        self.assertGreater(checked, 0)

    def test_text_hygiene(self):
        for path in markdown_files():
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(path.is_symlink())
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.endswith("\n"))
                self.assertNotIn("\x00", text)
                self.assertNotIn("[TODO:", text)
                self.assertNotIn("/Users/", text, "Public docs must not contain private machine paths")
                self.assertNotIn("/private/var/", text)
                for line in text.splitlines():
                    self.assertEqual(line.rstrip(), line, "Trailing whitespace")
                list(prose_lines(text))

    def test_client_pointers_share_one_source(self):
        self.assertEqual("@AGENTS.md\n", (ROOT / "CLAUDE.md").read_text())
        self.assertEqual("@./AGENTS.md\n", (ROOT / "GEMINI.md").read_text())

    def test_no_workflow_runtime_or_user_state_in_public_layout(self):
        for name in ("workbench", "contracts", "integrations", "plugins", "schemas"):
            self.assertFalse((ROOT / name).exists(), name)
        for folder in (ROOT / ".agents", ROOT / "docs", ROOT / "templates"):
            self.assertEqual([], list(folder.rglob("state.json")))
        self.assertIn(".workspace/", (ROOT / ".gitignore").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
