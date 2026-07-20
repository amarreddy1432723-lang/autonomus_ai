from __future__ import annotations

from pathlib import Path

from services.agent.arceus_runtime.repository.service import index_repository_path, search_index


def test_repository_intelligence_indexes_profile_symbols_imports_and_tests(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"next":"16.0.0","react":"19.0.0"},"devDependencies":{"typescript":"latest"}}',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "user.service.ts").write_text(
        "import { helper } from './helper';\nexport interface User {}\nexport class UserService {}\nexport function listUsers() { return helper(); }\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "helper.ts").write_text("export const helper = () => [];\n", encoding="utf-8")
    (tmp_path / "src" / "user.service.test.ts").write_text("import { listUsers } from './user.service';\ntest('users', () => listUsers());\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    result = index_repository_path(str(tmp_path), repository_id="repo_test")

    assert result["profile"]["repository_type"] == "application"
    assert any(item["name"] == "Next.js" for item in result["profile"]["frameworks"])
    assert any(symbol["name"] == "UserService" for symbol in result["symbols"])
    assert any(rel["kind"] == "imports" and "./helper" in rel["evidence"] for rel in result["relationships"])
    assert result["tests"][0]["target_paths"]
    assert "README.md" in result["documentation_paths"]

    search = search_index("repo_test", "UserService")
    assert search["results"]
