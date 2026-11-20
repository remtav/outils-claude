"""Tests de plugins/kalmia/hooks/garde-agents-vague.py par entrées JSON factices.

Lancer : python3 -m unittest discover -s tests/hooks -v
Repris de tests/hooks/test_agent_guard.py de remtav/template (règles implementeur et
reviseur, extraites de agent-guard.py). Les règles des autres agents restent dans
chaque projet : ici, on vérifie seulement que le garde du plugin les ignore.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUARD = os.path.join(ROOT, "plugins", "kalmia", "hooks", "garde-agents-vague.py")
HOOKS_JSON = os.path.join(ROOT, "plugins", "kalmia", "hooks", "hooks.json")


def run(agent_type, tool_name, tool_input, argv_agent=None):
    """Envoie une entrée factice au garde ; renvoie (code de sortie, stderr)."""
    event = {"tool_name": tool_name, "tool_input": tool_input, "cwd": ROOT}
    if agent_type is not None:
        event["agent_type"] = agent_type
    cmd = [sys.executable, GUARD] + ([argv_agent] if argv_agent else [])
    env = dict(os.environ, CLAUDE_PROJECT_DIR=ROOT)
    proc = subprocess.run(cmd, input=json.dumps(event), capture_output=True, text=True, env=env)
    return proc.returncode, proc.stderr


def bash(command):
    return ("Bash", {"command": command})


def write(path):
    return ("Write", {"file_path": path, "content": "x"})


MERGE = ("mcp__github__merge_pull_request", {"owner": "o", "repo": "r", "pullNumber": 1})
AUTO_MERGE = ("mcp__github__enable_pr_auto_merge", {"owner": "o", "repo": "r", "pullNumber": 1})
APPROVE = ("mcp__github__pull_request_review_write",
           {"method": "create", "owner": "o", "repo": "r", "pullNumber": 1, "event": "APPROVE"})
APPROVE_PENDING = ("mcp__github__pull_request_review_write",
                   {"method": "submit_pending", "owner": "o", "repo": "r", "pullNumber": 1, "event": "approve"})
REVIEW_COMMENT = ("mcp__github__pull_request_review_write",
                  {"method": "create", "owner": "o", "repo": "r", "pullNumber": 1, "event": "COMMENT", "body": "ok"})


def mcp_file(tool, branch):
    tool_input = {"owner": "o", "repo": "r", "path": "a.txt", "message": "m", "content": "x"}
    if tool == "mcp__github__push_files":
        tool_input = {"owner": "o", "repo": "r", "message": "m", "files": [{"path": "a", "content": "x"}]}
    if branch is not None:
        tool_input["branch"] = branch
    return (tool, tool_input)


MCP_FILE_TOOLS = ("mcp__github__push_files", "mcp__github__create_or_update_file", "mcp__github__delete_file")
NEW_AGENTS = ("implementeur", "reviseur", "kalmia:implementeur", "kalmia:reviseur")


class NewAgentsCommon(unittest.TestCase):
    """implementeur et reviseur : pas de fusion, pas d'approbation, pas de push sur main."""

    def assertBlocked(self, agent, call):
        code, err = run(agent, *call)
        self.assertEqual(code, 2, f"{agent} {call} devrait être bloqué (stderr: {err})")
        self.assertTrue(err.strip())

    def assertAllowed(self, agent, call):
        code, err = run(agent, *call)
        self.assertEqual(code, 0, f"{agent} {call} devrait passer (stderr: {err})")

    def test_bash_merge_blocked(self):
        for agent in NEW_AGENTS:
            self.assertBlocked(agent, bash("gh pr merge 12 --merge"))

    def test_bash_approve_blocked(self):
        for agent in NEW_AGENTS:
            self.assertBlocked(agent, bash("gh pr review 12 --approve"))

    def test_bash_push_main_blocked(self):
        for agent in NEW_AGENTS:
            self.assertBlocked(agent, bash("git push origin main"))
            self.assertBlocked(agent, bash("git push origin HEAD:refs/heads/master"))

    def test_bash_force_push_blocked(self):
        for agent in NEW_AGENTS:
            self.assertBlocked(agent, bash("git push --force origin 69-x"))

    def test_mcp_merge_blocked(self):
        for agent in NEW_AGENTS:
            self.assertBlocked(agent, MERGE)
            self.assertBlocked(agent, AUTO_MERGE)

    def test_mcp_approve_blocked(self):
        for agent in NEW_AGENTS:
            self.assertBlocked(agent, APPROVE)
            self.assertBlocked(agent, APPROVE_PENDING)

    def test_mcp_write_main_blocked(self):
        for agent in NEW_AGENTS:
            for tool in MCP_FILE_TOOLS:
                for branch in ("main", "master", "refs/heads/main", None, ""):
                    self.assertBlocked(agent, mcp_file(tool, branch))

    def test_argv_agent(self):
        # mode agent principal (`claude --agent implementeur`) : `garde-agents-vague.py <agent>`
        for agent in ("implementeur", "reviseur", "kalmia:implementeur", "kalmia:reviseur"):
            self.assertEqual(run(None, *MERGE, argv_agent=agent)[0], 2)
            self.assertEqual(run(None, *APPROVE, argv_agent=agent)[0], 2)
            self.assertEqual(run(None, *bash("git push origin main"), argv_agent=agent)[0], 2)

    def test_harmless_read_allowed(self):
        for agent in NEW_AGENTS:
            self.assertAllowed(agent, bash("git status && git log --oneline -3"))


class Implementeur(NewAgentsCommon):
    def test_commit_and_branch_push_allowed(self):
        for agent in ("implementeur", "kalmia:implementeur"):
            self.assertAllowed(agent, bash("git commit -m 'x' && git push -u origin 69-agents"))

    def test_write_anywhere_allowed(self):
        for agent in ("implementeur", "kalmia:implementeur"):
            self.assertAllowed(agent, write(".claude/commands/vague.md"))
            self.assertAllowed(agent, write("templates/projet/README.md"))

    def test_mcp_write_branch_allowed(self):
        for agent in ("implementeur", "kalmia:implementeur"):
            for tool in MCP_FILE_TOOLS:
                self.assertAllowed(agent, mcp_file(tool, "69-agents"))

    def test_review_comment_allowed(self):
        self.assertAllowed("implementeur", REVIEW_COMMENT)


class Reviseur(NewAgentsCommon):
    def test_no_commit_or_push(self):
        for agent in ("reviseur", "kalmia:reviseur"):
            self.assertBlocked(agent, bash("git commit -m x"))
            self.assertBlocked(agent, bash("git push -u origin 69-agents"))

    def test_no_file_write(self):
        for agent in ("reviseur", "kalmia:reviseur"):
            self.assertBlocked(agent, write("README.md"))
            self.assertBlocked(agent, ("Edit", {"file_path": ".claude/hooks/garde-agents-vague.py"}))

    def test_no_mcp_file_write_any_branch(self):
        for agent in ("reviseur", "kalmia:reviseur"):
            for tool in MCP_FILE_TOOLS:
                self.assertBlocked(agent, mcp_file(tool, "69-agents"))

    def test_comment_review_allowed(self):
        for agent in ("reviseur", "kalmia:reviseur"):
            self.assertAllowed(agent, REVIEW_COMMENT)
            self.assertAllowed(agent, bash("gh pr comment 12 --body 'PR #12 | approuvé'"))


class FailClosed(unittest.TestCase):
    def test_invalid_json_blocks(self):
        proc = subprocess.run([sys.executable, GUARD], input="pas du json", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_mcp_bad_input_blocks_new_agents(self):
        for agent in NEW_AGENTS:
            code, _ = run(agent, "mcp__github__push_files", ["pas", "un", "objet"])
            self.assertEqual(code, 2, agent)


class OtherAgentsIgnored(unittest.TestCase):
    """Le garde du plugin ne s'occupe que de implementeur et reviseur : tout le reste passe
    (les règles des autres agents restent dans le agent-guard.py de chaque projet)."""

    CASES = [
        ("gab", write("README.md")),
        ("gab", bash("git commit -m x")),
        ("jf", bash("git push origin main")),
        ("jf", MERGE),
        ("reviewer", bash("gh pr merge 3")),
        ("reviewer", APPROVE),
        (None, bash("gh pr merge 3")),
        (None, MERGE),
        (None, mcp_file("mcp__github__push_files", "main")),
        ("Explore", MERGE),
        ("autre:implementeur", MERGE),
        ("kalmia:release-mecanique", bash("git status")),
    ]

    def test_cases(self):
        for agent, call in self.CASES:
            with self.subTest(agent=agent, tool=call[0], input=call[1]):
                code, err = run(agent, *call)
                self.assertEqual(code, 0, err)

    def test_argv_other_agent(self):
        self.assertEqual(run(None, *bash("git push origin main"), argv_agent="jf")[0], 0)


class HooksJson(unittest.TestCase):
    """Le matcher du garde dans hooks.json couvre les outils sensibles, et lui seul."""

    def guard_matcher(self):
        with open(HOOKS_JSON, encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]
        entries = [e for e in hooks["PreToolUse"]
                   if any("garde-agents-vague.py" in h["command"] for h in e["hooks"])]
        self.assertEqual(len(entries), 1)
        return entries[0]["matcher"]

    def test_matcher_covers_tools(self):
        import re
        matcher = self.guard_matcher()
        tools = ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit",
                 "mcp__github__merge_pull_request", "mcp__github__enable_pr_auto_merge",
                 "mcp__github__pull_request_review_write") + MCP_FILE_TOOLS
        for tool in tools:
            self.assertTrue(re.fullmatch(matcher, tool), tool)
        for tool in ("Read", "SubagentHandback", "mcp__github__issue_read", "mcp__github__create_pull_request"):
            self.assertFalse(re.fullmatch(matcher, tool), tool)


if __name__ == "__main__":
    unittest.main()
