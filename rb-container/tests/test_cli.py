import os
from unittest.mock import patch
from click.testing import CliRunner

from repo_bridge.cli import cli
from repo_bridge.config import parse_config


def test_parse_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
target_dir: "./.repos"
repos:
  - name: "example-repo"
    url: "https://github.com/example/example-repo.git"
    auth_env_var: "MY_TOKEN"
    """)

    config = parse_config(str(config_file))
    assert config.target_dir == "./.repos"
    assert len(config.repos) == 1
    assert config.repos[0].name == "example-repo"
    assert config.repos[0].url == "https://github.com/example/example-repo.git"
    assert config.repos[0].auth_env_var == "MY_TOKEN"


@patch("repo_bridge.cli.subprocess.run")
def test_pull_command(mock_run, tmp_path):
    # Create a dummy config
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
target_dir: "./.repos"
repos:
  - name: "example-repo"
    url: "https://github.com/example/example-repo.git"
    """)

    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--config", str(config_file)])

    assert result.exit_code == 0
    assert "Target directory set to" in result.output
    assert "Cloning repository 'example-repo'" in result.output
    mock_run.assert_called_once()


@patch("langchain_core.prompts.PromptTemplate")
@patch("langchain_community.llms.Ollama")
def test_analyze_command(mock_ollama, mock_prompt, tmp_path):
    # Mock LLM and response
    mock_llm_instance = mock_ollama.return_value
    mock_llm_instance.invoke.return_value = "# Mocked Documentation"

    # Create dummy config
    config_file = tmp_path / "config.yaml"
    repo_dir = tmp_path / ".repos"
    docs_dir = tmp_path / "docs"
    repo_example_dir = repo_dir / "example-repo"

    # Create the repo directory to pass the 'os.path.exists' check in analyze
    repo_example_dir.mkdir(parents=True)

    config_file.write_text(f"""
target_dir: "{repo_dir}"
repos:
  - name: "example-repo"
    url: "https://github.com/example/example-repo.git"
    """)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["analyze", "--config", str(config_file), "--docs-dir", str(docs_dir)]
    )

    assert result.exit_code == 0
    assert "Analyzing repository: example-repo" in result.output
    assert (
        "Generating documentation for example-repo using model llama3" in result.output
    )
    assert "Successfully documented 'example-repo'" in result.output

    # Check if doc was created
    doc_path = docs_dir / "example-repo.md"
    assert doc_path.exists()
    assert doc_path.read_text() == "# Mocked Documentation"
