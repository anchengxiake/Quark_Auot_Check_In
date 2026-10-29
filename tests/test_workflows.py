import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

try:  # CI 安装 requirements-dev.txt，本地缺 PyYAML 时退回 ruamel.yaml
    import yaml

    def load_yaml(path):
        return yaml.safe_load(path.read_text(encoding="utf-8"))

except ModuleNotFoundError:  # pragma: no cover - 本地环境兜底
    from ruamel.yaml import YAML

    _yaml = YAML(typ="safe")

    def load_yaml(path):
        with path.open(encoding="utf-8") as handle:
            return _yaml.load(handle)


class WorkflowSyntaxTests(unittest.TestCase):
    def test_workflow_files_exist(self):
        names = {path.name for path in WORKFLOW_DIR.glob("*.yml")}
        self.assertIn("quark_signin.yml", names)
        self.assertIn("empty-commit-keepalive.yml", names)

    def test_all_workflows_are_valid_yaml_mappings(self):
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            with self.subTest(path=path.name):
                parsed = load_yaml(path)
                self.assertIsInstance(parsed, dict)
                self.assertIn("jobs", parsed)
                for job_name, job in parsed["jobs"].items():
                    self.assertIn("runs-on", job, f"{path.name}:{job_name} 缺少 runs-on")
                    for step in job.get("steps", []):
                        self.assertTrue(
                            "uses" in step or "run" in step,
                            f"{path.name}:{job_name} 存在空步骤 {step}",
                        )

    def test_signin_workflow_triggers(self):
        parsed = load_yaml(WORKFLOW_DIR / "quark_signin.yml")
        # PyYAML 会把裸 on 解析成 True，两种键名都兼容
        triggers = parsed.get("on", parsed.get(True))
        self.assertIsNotNone(triggers)
        crons = [entry["cron"] for entry in triggers["schedule"]]
        self.assertIn("0 1 * * *", crons)
        self.assertIn("0 5 * * *", crons)

    def test_signin_workflow_uses_read_only_permissions(self):
        parsed = load_yaml(WORKFLOW_DIR / "quark_signin.yml")
        self.assertEqual(parsed["permissions"]["contents"], "read")

    def test_keepalive_workflow_has_write_permission(self):
        parsed = load_yaml(WORKFLOW_DIR / "empty-commit-keepalive.yml")
        self.assertEqual(parsed["permissions"]["contents"], "write")


if __name__ == "__main__":
    unittest.main()
