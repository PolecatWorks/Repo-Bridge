import os
import subprocess
import click
from urllib.parse import urlparse

from .config import parse_config


def inject_auth_token(url: str, token: str) -> str:
    """Injects an authentication token into a Git URL."""
    parsed = urlparse(url)
    if not parsed.netloc:
        return url

    # If the URL already has some basic auth, we replace it, or just prepend the token
    # Format: https://<token>@github.com/user/repo.git
    auth_netloc = f"{token}@{parsed.netloc.split('@')[-1]}"
    return parsed._replace(netloc=auth_netloc).geturl()


@click.group()
def cli():
    """Repo-Bridge: A tool to pull and document Git repositories."""
    pass


@cli.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Path to the configuration YAML file.",
)
def pull(config):
    """Pull Git repositories defined in the configuration file."""
    try:
        project_config = parse_config(config)
    except Exception as e:
        click.echo(f"Error parsing configuration: {e}", err=True)
        raise click.Abort()

    target_dir = project_config.target_dir
    os.makedirs(target_dir, exist_ok=True)
    click.echo(f"Target directory set to: {target_dir}")

    for repo in project_config.repos:
        repo_path = os.path.join(target_dir, repo.name)
        clone_url = repo.url

        # Handle authentication if specified
        if repo.auth_env_var:
            token = os.environ.get(repo.auth_env_var)
            if token:
                clone_url = inject_auth_token(repo.url, token)
            else:
                click.echo(
                    f"Warning: Auth environment variable '{repo.auth_env_var}' not found for repo '{repo.name}'. Proceeding without it.",
                    err=True,
                )

        if os.path.exists(repo_path):
            click.echo(
                f"Repository '{repo.name}' already exists at {repo_path}. Pulling latest changes..."
            )
            try:
                # We do a git pull inside the repo directory
                subprocess.run(
                    ["git", "-C", repo_path, "pull"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                click.echo(f"Successfully pulled '{repo.name}'.")
            except subprocess.CalledProcessError as e:
                click.echo(f"Error pulling '{repo.name}': {e.stderr}", err=True)
        else:
            click.echo(f"Cloning repository '{repo.name}' into {repo_path}...")
            try:
                # We use clone_url which might contain the token.
                # Note: This might print the token if it fails, but subprocess.run hides stdout by default if not captured.
                # To be safer, we don't print the clone_url directly.
                subprocess.run(
                    ["git", "clone", clone_url, repo_path],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                click.echo(f"Successfully cloned '{repo.name}'.")
            except subprocess.CalledProcessError as e:
                # Be careful not to expose the token in the error message if possible
                error_msg = (
                    e.stderr.replace(clone_url, repo.url) if e.stderr else str(e)
                )
                click.echo(f"Error cloning '{repo.name}': {error_msg}", err=True)


@cli.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Path to the configuration YAML file.",
)
@click.option(
    "--model",
    "-m",
    default="llama3",
    help="The Ollama model to use for analysis (default: llama3)",
)
@click.option(
    "--docs-dir",
    "-d",
    default="docs",
    help="Directory to save the generated documentation (default: docs)",
)
def analyze(config, model, docs_dir):
    """Analyze cloned repositories and generate documentation using LLM."""
    try:
        from langchain_community.llms import Ollama
        from langchain_core.prompts import PromptTemplate
    except ImportError:
        click.echo(
            "Error: LangChain is not installed. Please install it with `pip install langchain langchain-community`.",
            err=True,
        )
        raise click.Abort()

    try:
        project_config = parse_config(config)
    except Exception as e:
        click.echo(f"Error parsing configuration: {e}", err=True)
        raise click.Abort()

    target_dir = project_config.target_dir
    os.makedirs(docs_dir, exist_ok=True)

    # Initialize the LLM
    try:
        llm = Ollama(model=model)
    except Exception as e:
        click.echo(f"Error initializing Ollama model '{model}': {e}", err=True)
        raise click.Abort()

    prompt_template = PromptTemplate(
        input_variables=["repo_name", "file_tree", "key_files_content"],
        template=(
            "You are a principal software engineer tasked with understanding and documenting a code repository.\n\n"
            "Repository Name: {repo_name}\n\n"
            "--- File Tree ---\n{file_tree}\n\n"
            "--- Key Files Content ---\n{key_files_content}\n\n"
            "Based on the file tree and the contents of these key files (such as README and package management files), "
            "provide a comprehensive overview of what this repository does. Include:\n"
            "1. An executive summary of its purpose.\n"
            "2. Its main features and capabilities.\n"
            "3. The primary technologies, frameworks, and tools used.\n"
            "4. A brief note on how to get started or install the project.\n\n"
            "Format the output strictly as Markdown."
        ),
    )

    for repo in project_config.repos:
        repo_path = os.path.join(target_dir, repo.name)
        if not os.path.exists(repo_path):
            click.echo(
                f"Warning: Repository '{repo.name}' not found at {repo_path}. Skipping...",
                err=True,
            )
            continue

        click.echo(f"Analyzing repository: {repo.name}...")

        # 1. Generate a file tree (simple os.walk)
        file_tree_lines = []
        for root, dirs, files in os.walk(repo_path):
            # Exclude .git directory
            if ".git" in dirs:
                dirs.remove(".git")

            rel_path = os.path.relpath(root, repo_path)
            if rel_path == ".":
                level = 0
            else:
                level = rel_path.count(os.sep) + 1

            indent = " " * 4 * (level)
            file_tree_lines.append(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 4 * (level + 1)
            for f in files:
                file_tree_lines.append(f"{subindent}{f}")

        # Limit the file tree output size to avoid blowing up context window on massive repos
        file_tree = "\n".join(file_tree_lines[:500])
        if len(file_tree_lines) > 500:
            file_tree += "\n... (truncated)"

        # 2. Read key files
        key_files = [
            "README.md",
            "README",
            "readme.md",
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "Cargo.toml",
            "go.mod",
            "Makefile",
        ]
        key_files_content = ""
        for kf in key_files:
            kf_path = os.path.join(repo_path, kf)
            if os.path.exists(kf_path):
                try:
                    with open(kf_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Simple truncation per file (approx 10,000 chars)
                        if len(content) > 10000:
                            content = content[:10000] + "\n... (truncated)"
                        key_files_content += f"\n--- {kf} ---\n{content}\n"
                except Exception as e:
                    click.echo(f"Could not read {kf} in {repo.name}: {e}", err=True)

        # 3. Invoke LLM
        prompt = prompt_template.format(
            repo_name=repo.name,
            file_tree=file_tree,
            key_files_content=key_files_content,
        )

        try:
            click.echo(
                f"Generating documentation for {repo.name} using model {model}..."
            )
            response = llm.invoke(prompt)

            # 4. Save documentation
            doc_path = os.path.join(docs_dir, f"{repo.name}.md")
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(response)
            click.echo(f"Successfully documented '{repo.name}' -> {doc_path}")
        except Exception as e:
            click.echo(
                f"Error communicating with Ollama for repo '{repo.name}'. "
                f"Make sure Ollama is running and the model '{model}' is available locally: {e}",
                err=True,
            )


if __name__ == "__main__":
    cli()
