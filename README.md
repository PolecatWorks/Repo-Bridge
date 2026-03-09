# Repo-Bridge

Repo-Bridge is a Python CLI tool designed to pull down Git repositories, read the source code, and automatically document what the repository does based on its code. It helps in understanding how different repositories relate to one another.

## Features

* **Repository Analysis**: Pulls down Git repositories and reads the source code.
* **Documentation Generation**: Documents repository functionality intelligently.
* **Extraction**: Automatically extracts APIs, specifications, and schemas from the codebase.

## Technical Details

* Built as a Python CLI.
* Utilizes `click` for the command-line interface.
* Uses `pydantic` for data validation and schema definitions.
