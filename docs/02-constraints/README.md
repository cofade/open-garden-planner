# 2. Constraints

## 2.1 Technical Constraints

| Constraint | Description |
|------------|-------------|
| **Python 3.11+** | Minimum Python version; leverages modern type hint features and performance improvements |
| **PyQt6 (GPLv3)** | GUI framework choice requires GPLv3 licensing for the project |
| **Desktop Application** | Must run as a native desktop app, not a web application |
| **Windows Primary** | Primary target platform is Windows 10/11; cross-platform support is future work |
| **Offline Capable** | Core functionality must work without internet; plant API is optional enhancement |
| **JSON Project Format** | Project files must be human-readable JSON (.ogp) for transparency and VCS compatibility |

## 2.2 Organizational Constraints

| Constraint | Description |
|------------|-------------|
| **Open Source (GPLv3)** | Project must remain GPLv3-licensed; all dependencies must be compatible |
| **Small Team** | Primary development by 1-2 contributors; architecture must support external contributions |
| **No Budget** | No paid assets, services, or infrastructure; all dependencies must be free/open |
| **AI-Assisted Development** | AI coding tools are encouraged; quality standards apply regardless of how code is produced |

## 2.3 Convention Constraints

| Constraint | Description |
|------------|-------------|
| **Code Quality** | All Python code: type hints, ruff linting, Black formatting |
| **Testing** | All features require unit, integration, and UI tests; >80% coverage on non-UI code |
| **Git Workflow** | Feature branches, PR-based merges, no direct commits to master |
| **Commit Style** | Conventional commits: `feat(US-X.X): Description` |

## 2.4 Licensing

**GNU General Public License v3 (GPLv3)** — Confirmed

Rationale:
- Required for PyQt6 (unless commercial license purchased)
- Ensures derivative works remain open source
- Strong copyleft protects project from proprietary forks
- Well-understood in open source community
