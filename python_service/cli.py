import sys
import os
import asyncio
import json
import click
from dotenv import load_dotenv

# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Load env BEFORE imports so singletons (e.g. llm_gateway) can read API keys
load_dotenv(os.path.join(root_dir, ".env"), override=True)

from python_service.app.db.sqlite import init_db, build_session_factory
from python_service.app.db.repositories.job_repo import JobRepository
from python_service.app.services.market_snapshot_service import MarketSnapshotService
from python_service.app.services.analysis_job_service import AnalysisJobService
from python_service.app.services.market_data_service import market_data_service
from python_service.app.lake.parquet_store import ParquetMarketStore

CONFIG_FILE = os.path.expanduser("~/.alsa_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

@click.group()
def cli():
    """ALSA Institutional CLI - Professional Equity Research."""
    pass

@cli.group()
def config():
    """Manage CLI configuration."""
    pass

@config.command()
def show():
    """View current settings."""
    cfg = load_config()
    if not cfg:
        click.echo("No configuration found.")
        return
    for k, v in cfg.items():
        if "api_key" in k.lower():
            click.echo(f"{k}: {'*' * 8}{v[-4:] if v else ''}")
        else:
            click.echo(f"{k}: {v}")

@config.command()
@click.argument("key")
@click.argument("value")
def set(key, value):
    """Set a configuration value."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    click.echo(f"Set {key} to {value}")

@cli.command()
@click.argument("query")
@click.option("--market", "-m", default=None, help="Explicit market (A-Share, HK-Share, US-Share).")
@click.option("--level", "-l", default="standard", type=click.Choice(["quick", "standard", "deep"]), help="Analysis depth.")
@click.option("--output", "-o", default=None, help="Custom path for HTML report.")
@click.option("--model", "-model", default=None, help="Gemini model version (e.g. 1.5-pro, 2.0-flash).")
def analyze(query, market, level, output, model):
    """Analyze a stock and generate an HTML report."""
    click.echo(f"Starting analysis for: {query} (Level: {level})")
    
    # Run async logic
    asyncio.run(run_analysis_flow(query, market, level, output, model))


@cli.command("sector")
@click.argument("sector_name", required=False, default=None)
@click.option("--output", "-o", default=None, help="Custom path for HTML report.")
@click.option("--model", "-model", default=None, help="LLM model to use.")
def sector_analyze(sector_name, output, model):
    """Analyze a sector/industry and recommend 5-10 stocks.
    
    If SECTOR_NAME is omitted, runs a market scan first to recommend sectors."""
    if sector_name:
        click.echo(f"Starting sector analysis for: {sector_name}")
        asyncio.run(run_sector_flow(sector_name, output, model))
    else:
        click.echo("No sector specified. Running market scan to recommend sectors...")
        asyncio.run(run_market_scan_then_sector(output, model))

async def run_analysis_flow(query, market, level, output_path, model):
    # 1. Initialize dependencies
    from python_service.app.db.sqlite import DATABASE_URL
    session_factory = build_session_factory(DATABASE_URL)
    job_repo = JobRepository(session_factory)
    parquet_store = ParquetMarketStore()
    snapshot_service = MarketSnapshotService(parquet_store)
    
    service = AnalysisJobService(job_repo, snapshot_service)
    
    # 2. Resolve Symbol (Smart Recognition)
    click.echo(f"Searching for asset: {query}...")
    matches = await market_data_service.resolve_symbol(query, market)
    
    if not matches:
        click.echo(f"Error: Could not find any assets matching '{query}'.")
        return
    
    selected_match = matches[0]
    if len(matches) > 1:
        click.echo("\nMultiple matches found. Please choose:")
        for i, m in enumerate(matches):
            click.echo(f"{i+1}. {m['name']} ({m['symbol']} | {m['market']})")
        
        choice = click.prompt("Enter ID to select", type=int, default=1)
        if 1 <= choice <= len(matches):
            selected_match = matches[choice-1]
        else:
            click.echo("Invalid choice. Using the first match.")

    symbol = selected_match["symbol"]
    resolved_market = selected_match["market"]
    click.echo(f"Selected: {selected_match['name']} ({symbol} | {resolved_market})")
    
    # Use model from CLI option or config; if None, discussion_service uses .env default
    cfg = load_config()
    final_model = model or cfg.get("model") or cfg.get("gemini_model")
    if final_model and final_model == "gemini-1.5-pro":
        # gemini-1.5-pro is deprecated, fall back to env default
        final_model = None
    
    # 3. Start Job
    click.echo("\nFetching data and running expert discussion...")
    job_id = await service.start_job(symbol, resolved_market, level=level, model=final_model)
    click.echo(f"Job ID: {job_id}")
    
    # 4. Wait for completion (polling)
    last_status = None
    while True:
        job_status = service.get_status(job_id)
        if not job_status:
            click.echo("\nError: Job vanished from database.")
            return
            
        if job_status.status != last_status:
            click.echo(f"\nStatus: {job_status.status}", nl=False)
            last_status = job_status.status
        else:
            click.echo(".", nl=False)
            
        if job_status.status == "completed":
            click.echo("\nAnalysis completed successfully!")
            analysis_data = service.get_analysis_run(job_status.analysis_id)
            break
        elif job_status.status == "failed":
            click.echo(f"\nAnalysis failed: {job_status.error_message or 'Unknown error'}")
            return
        elif job_status.status == "cancelled":
            click.echo("\nAnalysis was cancelled.")
            return
            
        await asyncio.sleep(2)

    # 5. Generate HTML Report
    click.echo(f"Generating HTML report...")
    from python_service.app.services.report_generator_service import ReportGeneratorService
    
    report_service = ReportGeneratorService()
    
    final_output = output_path or f"{symbol}_report.html"
    try:
        html_path = await report_service.generate_html_report_async(analysis_data, final_output, model=final_model)
        click.echo(f"Success! Report generated at: {html_path}")
    except Exception as e:
        click.echo(f"Report generation failed: {e}")


async def run_sector_flow(sector_name, output_path, model):
    """Run sector analysis flow: snapshot → expert discussion → report."""
    from python_service.app.db.sqlite import DATABASE_URL
    session_factory = build_session_factory(DATABASE_URL)
    job_repo = JobRepository(session_factory)
    from python_service.app.services.sector_analysis_service import SectorAnalysisService

    service = SectorAnalysisService(job_repo)

    # Use model from CLI option or config
    cfg = load_config()
    final_model = model or cfg.get("model") or cfg.get("gemini_model")
    if final_model and final_model == "gemini-1.5-pro":
        final_model = None

    click.echo(f"\nBuilding sector snapshot and running expert discussion for: {sector_name}")
    job_id = await service.start_sector_job(sector_name, model=final_model)
    click.echo(f"Job ID: {job_id}")

    # Wait for completion (polling)
    last_status = None
    while True:
        job_status = job_repo.get_by_id(job_id)
        if not job_status:
            click.echo("\nError: Job vanished from database.")
            return

        if job_status.status != last_status:
            progress = service.get_progress(job_id)
            msg = progress.get("message", job_status.status)
            click.echo(f"\nStatus: {job_status.status} | {msg}", nl=False)
            last_status = job_status.status
        else:
            click.echo(".", nl=False)

        if job_status.status == "completed":
            click.echo("\nSector analysis completed successfully!")
            break
        elif job_status.status == "failed":
            click.echo(f"\nSector analysis failed: {job_status.error_message or 'Unknown error'}")
            return
        elif job_status.status == "cancelled":
            click.echo("\nSector analysis was cancelled.")
            return

        await asyncio.sleep(2)

    # Generate HTML Report
    click.echo("Generating sector HTML report...")
    from python_service.app.services.sector_report_service import SectorReportService

    report_service = SectorReportService()
    result = service.get_result(job_id)

    if not result:
        # Fallback: get from DB
        import json as _json
        if job_status.result_payload:
            result = _json.loads(job_status.result_payload)

    if not result:
        click.echo("Error: No result data available for report generation.")
        return

    final_output = output_path or f"sector_{sector_name}_report.html"
    try:
        html_path = await report_service.generate_sector_report(result, final_output, model=final_model)
        click.echo(f"Success! Sector report generated at: {html_path}")
    except Exception as e:
        click.echo(f"Sector report generation failed: {e}")


async def run_market_scan_then_sector(output_path, model):
    """Step 1: Scan market for promising sectors. Step 2: User picks one. Step 3: Deep sector analysis."""
    from python_service.app.services.llm_gateway import llm_gateway
    from python_service.app.prompting.runtime import prompt_runtime

    cfg = load_config()
    final_model = model or cfg.get("model") or cfg.get("gemini_model")
    if final_model and final_model == "gemini-1.5-pro":
        final_model = None
    if not final_model:
        import os
        default_provider = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek").lower()
        if default_provider == "deepseek":
            final_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        else:
            final_model = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

    click.echo("\n📡 正在扫描A股市场板块轮动...")
    click.echo("(使用LLM + 实时搜索分析当前最具投资价值的板块)\n")

    # Load market scanner prompt
    try:
        prompt_data = prompt_runtime.get_prompt("market_sector_scanner")
        template = prompt_data["template"]
    except Exception as e:
        click.echo(f"Error loading market scanner prompt: {e}")
        return

    # Build context
    from datetime import datetime
    context = f"""
--- SYSTEM DIRECTIVE ---
You are an institutional-grade AI analyst. You MUST use web_search to get real-time data. NEVER fabricate data.

--- SYSTEM INSTRUCTIONS ---
{template}

--- CONTEXT ---
Current Date: {datetime.now().strftime('%Y-%m-%d')}
Market: A-Share (中国A股)
"""

    # Run with tool-calling (web_search enabled)
    click.echo("正在搜索和分析...")
    try:
        use_tools = "deepseek" in final_model.lower()
        if use_tools:
            scan_result = await llm_gateway.generate_with_tools(context, model=final_model, max_tool_rounds=5)
        else:
            scan_result = await llm_gateway.generate_content(context, model=final_model)
    except Exception as e:
        click.echo(f"Market scan failed: {e}")
        return

    if not scan_result:
        click.echo("Market scan returned empty result.")
        return

    # Display results
    click.echo("\n" + "=" * 60)
    click.echo("📊 A股板块扫描结果")
    click.echo("=" * 60)
    click.echo(scan_result)
    click.echo("=" * 60)

    # Extract sector names from the output for selection
    import re
    # Only match from the 7-column recommendation table (section 3) — not 3-column summary
    # Require at least 5 pipe separators in the row to distinguish from summary tables
    sector_lines = re.findall(r'(\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|)', scan_result)
    sectors = []
    seen = set()
    for line in sector_lines:
        m = re.match(r'\|\s*(?:⭐?\d+)\s*\|\s*([^|]+?)\s*\|', line)
        if m:
            name = m.group(1).strip().replace('**', '').strip()
            if len(name) >= 2 and not name.startswith('排序') and name not in seen:
                seen.add(name)
                sectors.append(name)

    if not sectors:
        # Fallback: ask user to type sector name manually
        sector_name = click.prompt("\n请输入要深入分析的板块名称")
    else:
        click.echo("\n请选择要深入分析的板块:")
        for i, s in enumerate(sectors):
            click.echo(f"  {i+1}. {s}")
        click.echo(f"  0. 退出")

        choice = click.prompt("输入编号选择", type=int, default=1)
        if choice == 0:
            click.echo("已退出。")
            return
        if 1 <= choice <= len(sectors):
            sector_name = sectors[choice - 1]
        else:
            click.echo("无效选择，使用第一个板块。")
            sector_name = sectors[0]

    click.echo(f"\n选择板块: {sector_name}")
    click.echo("开始深入板块分析...\n")

    await run_sector_flow(sector_name, output_path, model)


if __name__ == "__main__":
    cli()
