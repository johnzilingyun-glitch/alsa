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
from python_service.app.services.market_snapshot_service import market_snapshot_service
from python_service.app.services.analysis_job_service import AnalysisJobService
from python_service.app.services.market_data_service import market_data_service

# Load env
load_dotenv(os.path.join(root_dir, ".env"), override=True)

CONFIG_FILE = os.path.expanduser("~/.alsa_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
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
def analyze(query, market, level, output):
    """Analyze a stock and generate an HTML report."""
    click.echo(f"Starting analysis for: {query} (Level: {level})")
    
    # Run async logic
    asyncio.run(run_analysis_flow(query, market, level, output))

async def run_analysis_flow(query, market, level, output_path):
    # 1. Initialize dependencies
    # We need a session factory for the repository
    from python_service.app.db.sqlite import DATABASE_URL
    session_factory = build_session_factory(DATABASE_URL)
    job_repo = JobRepository(session_factory)
    
    service = AnalysisJobService(job_repo, market_snapshot_service)
    
    # 2. Resolve Symbol (simple placeholder logic, can be improved with search_service)
    # If query is a code, use it. If name, search.
    symbol = query
    resolved_market = market or "US-Share"
    
    if any('\u4e00' <= char <= '\u9fff' for char in query):
        # Chinese name, likely A-Share
        resolved_market = market or "A-Share"
        # Search would go here
    
    # 3. Start Job
    click.echo("Fetching data and running expert discussion...")
    job_id = await service.start_job(symbol, resolved_market, level=level)
    
    # 4. Wait for completion (polling)
    while True:
        status_data = service.get_status(job_id)
        if status_data.status == "completed":
            click.echo("\nAnalysis completed successfully!")
            result = json.loads(status_data.result_payload)
            break
        elif status_data.status == "failed":
            click.echo(f"\nAnalysis failed: {status_data.result_payload}")
            return
        
        click.echo(".", nl=False)
        await asyncio.sleep(2)

    # 5. Generate HTML Report
    click.echo(f"Generating HTML report...")
    from python_service.app.services.report_generator_service import ReportGeneratorService
    
    # Since report_generator_service.py was missing, I'll need to create it.
    # For now, let's assume it exists or we create it next.
    report_service = ReportGeneratorService()
    
    final_output = output_path or f"{symbol}_report.html"
    html_path = await report_service.generate_html_report_async(result, final_output)
    
    click.echo(f"Report generated: {html_path}")

if __name__ == "__main__":
    cli()
