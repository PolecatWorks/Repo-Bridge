import yaml
from pydantic import BaseModel, Field
from typing import List, Optional

class RepoConfig(BaseModel):
    name: str = Field(..., description="Name of the repository")
    url: str = Field(..., description="Git URL of the repository")
    auth_env_var: Optional[str] = Field(
        None, description="Environment variable containing the PAT or auth token"
    )


class ProjectConfig(BaseModel):
    target_dir: str = Field(
        ..., description="Target directory where repositories will be cloned"
    )
    repos: List[RepoConfig] = Field(
        default_factory=list, description="List of repositories to clone and analyze"
    )


def parse_config(config_path: str) -> ProjectConfig:
    """Parses a YAML configuration file and returns a validated ProjectConfig."""
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    return ProjectConfig(**data)
