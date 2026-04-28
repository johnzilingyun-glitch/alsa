# ALSA Institutional CLI User Guide

The ALSA CLI is a powerful terminal-based tool for professional equity research. It allows you to run deep-dive analyses, configure institutional parameters, and generate standalone research reports.

## 1. Installation & Setup
Ensure you are in the project root and your virtual environment is active:
```powershell
# Activate environment
.\.venv\Scripts\activate

# Basic test
python python_service/cli.py --help
```

## 2. Configuration (`config`)
Before running your first analysis, configure your credentials and preferences. Settings are persisted in `~/.alsa_config.json`.

| Command | Description |
| :--- | :--- |
| `python python_service/cli.py config show` | View current settings (API keys are masked) |
| `python python_service/cli.py config set gemini_api_key "KEY"` | Set your Gemini API key |
| `python python_service/cli.py config set gemini_model "3.0"` | Switch between `3.1` (flagship) and `3.0` models |
| `python python_service/cli.py config set debug_mode true` | Enable detailed terminal logging |
| `python python_service/cli.py config set feishu_url "URL"` | Configure Feishu Webhook for report distribution |

## 3. Stock Analysis (`analyze`)
The `analyze` command uses **Smart Recognition**. You don't need to remember codes; just type the name.

### Basic Usage
```powershell
python python_service/cli.py analyze "贵州茅台"
```

### Interactive Resolution
If you enter an abbreviation (e.g., "腾讯"), the CLI will prompt you to choose the correct asset:
```text
Multiple matches found. Please choose:
1. 腾讯控股 (00700 | HK-Share)
2. 腾讯音乐 (TME | US-Share)
Enter ID to select [1]: 1
```

### Options
- `--market` / `-m`: Explicitly set market (A-Share, HK-Share, US-Share).
- `--level` / `-l`: Analysis depth (`quick`, `standard`, `deep`).
- `--output` / `-o`: Custom path for the HTML report.

## 4. Report Location
By default, ALSA generates a standalone HTML research report.

- **Default Location**: The **Current Working Directory** where you ran the command.
- **Default Filename**: `[SYMBOL]_report.html` (e.g., `600519_report.html`).
- **Custom Location**:
  ```powershell
  python python_service/cli.py analyze "AAPL" -o ./reports/apple_june_report.html
  ```

---

## 5. Troubleshooting
- **Network Errors**: If data acquisition fails, ALSA will retry up to 3 times automatically. Ensure your internet connection is stable.
- **API Key Invalid**: If you see `API_KEY_INVALID`, use the `config set` command to update your key.
- **Garbled Text**: The CLI is optimized for UTF-8. On Windows, the tool automatically attempts to fix console encoding for emojis and Chinese characters.
