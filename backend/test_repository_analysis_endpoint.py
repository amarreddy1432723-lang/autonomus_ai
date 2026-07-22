from __future__ import annotations

from pathlib import Path

from services.agent.repository_analysis import RepositoryAnalyzeRequest, analyze_repository_path


def test_repository_analysis_returns_workspace_summary(tmp_path: Path):
    (tmp_path / "frontend" / "src" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "services" / "auth").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"next":"16.0.0","react":"19.0.0","@clerk/nextjs":"latest"},"scripts":{"build":"next build","test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi\npsycopg\npyjwt\nredis\n", encoding="utf-8")
    (tmp_path / "frontend" / "src" / "app" / "page.tsx").write_text("export default function Page() { return null }\n", encoding="utf-8")
    (tmp_path / "backend" / "services" / "auth" / "main.py").write_text(
        "from fastapi import FastAPI\nimport jwt\napp = FastAPI()\n@app.get('/health')\ndef health(): return {'ok': True}\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_auth.py").write_text("def test_smoke(): assert True\n", encoding="utf-8")

    result = analyze_repository_path(RepositoryAnalyzeRequest(workspace_id="local-fixture", root_path=str(tmp_path)))

    assert result["status"] == "completed"
    assert "TypeScript" in result["languages"]
    assert "Python" in result["languages"]
    assert "Next.js" in result["frameworks"]
    assert "FastAPI" in result["frameworks"]
    assert "npm" in result["package_managers"]
    assert "pip" in result["package_managers"]
    assert "frontend/src/app/page.tsx" in result["entry_points"]
    assert "PostgreSQL" in result["database_usage"]
    assert "JWT" in result["authentication"]
    assert result["test_commands"]
    assert "summary" in result
