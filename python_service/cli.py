import sys
import os
import asyncio
import json
import click
from dotenv import load_dotenv

# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from python_service.app.db.sqlite import init_db, build_session_factory
from python_service.app.db.repositories.job_repo import JobRepository
from python_service.app.services.market_snapshot_service import MarketSnapshotService
from python_service.app.services.analysis_job_service import AnalysisJobService
from python_service.app.services.market_data_service import market_data_service
from python_service.app.lake.parquet_store import ParquetMarketStore

# Load env
load_dotenv(os.path.join(root_dir, ".env"), override=True)

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
    
    # Use model from CLI option or config or default
    cfg = load_config()
    final_model = model or cfg.get("gemini_model")
    
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

if __name__ == "__main__":
    cli()
