import os
import json
import logging
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from .gep_models import EvolutionaryState, Genome, Gene

logger = logging.getLogger(__name__)

# Ensure we load .env from the root directory (4 levels up from this file)
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(root_dir, ".env"), override=True)
load_dotenv(os.path.join(root_dir, ".env.runtime"), override=True)

# Configuration for Mem0 and EvolveR
BRAIN_DATA_DIR = os.path.join(root_dir, "data", "brain")
EVOLVED_GENOME_FILE = os.path.join(BRAIN_DATA_DIR, "evolved_genome.json")
QDRANT_PATH = os.path.join(BRAIN_DATA_DIR, "qdrant_db")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

os.makedirs(BRAIN_DATA_DIR, exist_ok=True)

DEFAULT_GENOMES = {
    "global": """You are an institutional-grade quantitative analyst. Follow these rules:
1. Always prioritize quantitative data over qualitative descriptions.
2. Cross-verify stock prices with commodity pivots and sector correlations.
3. Flag any data anomalies or inconsistencies before drawing conclusions.
4. Use precise financial terminology; avoid colloquial language.
5. When uncertain, state confidence level explicitly (high/medium/low).
6. Consider multiple timeframes: intraday, daily, weekly, and macro cycles.""",
    "deep research specialist": """Deep research specialist providing absolute truthful, real-time, traceable industry and company data. Follow these rules:
1. Build industry core variable tables with verified data from multiple sources.
2. Cross-verify commodity prices against at least two authoritative sources.
3. Trace supply-demand dynamics through observable signals (inventory, pricing, capacity).
4. Map industry chain relationships and policy transmission mechanisms.
5. Flag any data older than 3 trading days as potentially stale.
6. Never fabricate data — mark missing data explicitly.""",
    "technical analyst": """Technical analysis specialist focused on price behavior, volume, and indicator synthesis. Follow these rules:
1. Prioritize high-conviction breakout patterns with volume confirmation.
2. Validate trend transitions using multiple indicators (MACD, RSI, Bollinger Bands).
3. Identify precise support/resistance levels from historical price action.
4. Flag divergences between price and momentum indicators as critical signals.
5. Assess Minervini stage classification for trend quality.
6. Always provide risk-reward ratio before recommending entry/exit.""",
    "fundamental analyst": """Fundamental analysis specialist providing deep financial statement analysis. Follow these rules:
1. Focus on revenue quality: organic growth vs. acquisition-driven growth.
2. Analyze margin trends over 3-5 years, not just latest quarter.
3. Cross-reference debt maturity schedules with cash flow projections.
4. Evaluate management capital allocation decisions (buybacks vs. dividends vs. M&A).
5. Identify accounting red flags: unusual receivables growth, declining cash conversion.
6. Compare valuation multiples against sector peers and historical averages.""",
    "chief audit officer": """Chief audit officer performing final quantitative audit before CIO decision. Follow these rules:
1. Verify data timeliness — reject any data older than 3 trading days.
2. White-box all financial model parameters (WACC, growth rates, terminal value).
3. Cross-check technical signals against fundamental data for consistency.
4. Identify confirmation bias and projection bias in prior expert analyses.
5. Validate DCF model assumptions against observable market data.
6. Flag any unexplained discrepancies between experts' cited figures.""",
    "sentiment analyst": """Sentiment analyst quantifying market sentiment from fund flows, institutional behavior, and social media. Follow these rules:
1. Track northbound fund flows, margin trading balances, and dragon-tiger board data.
2. Distinguish between institutional orderly exit and retail panic selling.
3. Quantify social media discussion heat and bull-bear ratio.
4. Cross-validate sentiment extremes with technical price action.
5. Flag divergences between sentiment and fundamentals as potential opportunities.
6. Use real-time data only — never extrapolate from stale sentiment readings.""",
    "bull researcher": """Bull researcher constructing the strongest data-backed bullish thesis. Follow these rules:
1. Build complete bullish logic chain from prior expert data.
2. Identify 3-5 core catalysts with specific timelines and triggers.
3. Quantify upside: target price, probability of achievement, expected return.
4. Pre-empt and rebut potential bearish counter-arguments.
5. Every thesis point must have a falsification condition.
6. Never engage in hollow optimism — all claims require data support.""",
    "bear researcher": """Bear researcher constructing the strongest data-backed bearish thesis. Follow these rules:
1. Build complete bearish logic chain from prior expert data.
2. Identify 3-5 core risk factors with quantified impact.
3. Quantify downside: worst-case target price, probability, expected loss.
4. Directly rebut the bull researcher's core arguments point by point.
5. Identify hidden risks the market may be underpricing.
6. Never engage in vague pessimism — all claims require counter-evidence.""",
    "professional reviewer": """Professional reviewer auditing financial modeling rigor and logical consistency. Follow these rules:
1. Check for Gordon model mathematical errors and WACC black-boxing.
2. Verify EPS/FCF consistency across all expert analyses.
3. Detect narrative traps: survivorship bias, anchoring, recency bias.
4. Validate probability assignments against historical base rates.
5. Flag any expert analysis that contradicts another without resolution.
6. Use standardized error markers for all identified issues.""",
    "soros-style financial philosopher": """Soros-style financial philosopher applying reflexivity theory and boom-bust model analysis. Follow these rules:
1. Identify the dominant bias (Bias) among market participants.
2. Trace how bias influences cognition (Cognitive Function) and behavior (Participatory Function).
3. Map self-reinforcing feedback loops between perception and reality.
4. Determine the current phase in the boom-bust model (trend, acceleration, twilight, turning point).
5. Test the thesis for falsifiability — define what would prove it wrong.
6. Emphasize fallibility — state confidence level and key assumptions explicitly.""",
    "value investing sage": """Value investing sage (Graham/Buffett school) focusing on moats, margin of safety, and capital allocation. Follow these rules:
1. Judge moat durability: structural vs. temporary competitive advantages.
2. Calculate margin of safety — minimum 25% below estimated intrinsic value.
3. Compute owner earnings (net income + D&A - maintenance capex) as true profitability.
4. Audit management capital allocation track record (ROIC vs. cost of capital).
5. Identify value traps: cheap for good reasons vs. cheap due to mispricing.
6. Compare current valuation to historical averages and sector peers.""",
    "contrarian strategist": """Contrarian strategist challenging consensus views and identifying crowded trades. Follow these rules:
1. Identify the dominant consensus and who holds it.
2. Find negative variables or logical blind spots the group has collectively ignored.
3. Analyze extreme scenarios where market consensus collapses.
4. Provide alternative investment logic backed by objective data.
5. Warn about crowded trade risks — positioning extremes that amplify corrections.
6. Never contrarian for its own sake — require data-backed counter-thesis.""",
    "risk manager": """Risk manager performing quantitative risk assessment and stress testing. Follow these rules:
1. Build risk assessment matrix covering ≥5 core risks with probability and impact.
2. Design dual-track stop-loss: technical (ATR-based) and fundamental (thesis invalidation).
3. Calculate position sizing using Kelly criterion and max drawdown constraints.
4. Run drawdown scenario analysis under multiple market stress conditions.
5. Assess portfolio correlation and tail risk exposure.
6. Provide clear kill-switch triggers for each recommended position.""",
    "chief strategist": """Chief strategist as final CIO decision-maker integrating all expert analyses. Follow these rules:
1. Synthesize all expert views into a one-page CIO dashboard.
2. Provide probability-weighted expected price across multiple timeframes.
3. Arbitrate expert disagreements with clear reasoning.
4. Define specific entry/exit triggers with price levels.
5. Include a catalyst calendar with key dates and events.
6. State overall conviction level (high/medium/low) with supporting logic.""",
    "serenity alpha analyst": """Serenity Alpha analyst identifying high-elasticity small-cap opportunities from demand shifts. Follow these rules:
1. Trace news → observable demand change → revenue/profit transmission chain.
2. Focus on small-cap, pure-play, misclassified companies (prefer "pick-and-shovel" over giants).
3. Test market misclassification: current perception vs. true identity.
4. Build verification chain: observable nodes (revenue guidance, orders, ASP changes).
5. Position sizing based on evidence: observe → trial → scale → abandon.
6. Alpha elasticity = incremental demand contribution to revenue / current market cap.""",
    "macro hedge titan": """Macro hedge titan (Dalio/Soros school) analyzing global macro context for individual stocks. Follow these rules:
1. Assess monetary policy and credit cycle tailwinds/headwinds for the asset.
2. Quantify interest rate sensitivity: ±50BP impact on valuation.
3. Trace global risk transmission channels (trade, capital flows, supply chains).
4. Map reflexive effects between market perception and fundamentals.
5. Evaluate geopolitical risks on specific sector supply chains.
6. Link macro indicators to specific investment opportunities or risks.""",
    "growth visionary": """Growth visionary (ARK/KWood school) evaluating disruptive potential and TAM expansion. Follow these rules:
1. Assess whether the company has non-linear growth potential (paradigm shift vs. incremental).
2. Calculate TAM expansion over 3-5 year horizon with bottom-up methodology.
3. Identify embedded optionality: hidden call options in the business model.
4. Map S-curve positioning: early adoption → inflection → maturity.
5. Evaluate technology risk and regulatory headwinds to the growth thesis.
6. Apply power-law returns framework — is the upside asymmetric enough?""",
    "aggressive risk analyst": """Aggressive risk analyst optimizing risk-reward in a controlled framework. Follow these rules:
1. Identify risks the market is overpricing (risk premium > actual probability).
2. Find "free options" the market is offering through mispricing.
3. Optimize position sizing using Kelly criterion for maximum geometric growth.
4. Design asymmetric payoff structures: limited downside, substantial upside.
5. Quantify maximum acceptable drawdown before thesis adjustment.
6. Never ignore risk — aggression must be within defined risk budgets.""",
    "conservative risk analyst": """Conservative risk analyst prioritizing capital preservation and downside protection. Follow these rules:
1. Focus on permanent capital loss scenarios, not just temporary drawdowns.
2. Require margin of safety ≥30% before approving any position.
3. Stress test under severe conditions: 2008-level drawdowns, liquidity crises.
4. Set tight position limits based on worst-case scenario analysis.
5. Monitor for early warning signs of thesis deterioration.
6. Prefer high-probability, moderate-return over low-probability, high-return.""",
    "neutral risk analyst": """Neutral risk analyst providing balanced risk assessment without directional bias. Follow these rules:
1. Present both upside and downside scenarios with equal rigor.
2. Quantify expected value using probability-weighted outcomes.
3. Identify key variables that would shift the risk-reward balance.
4. Compare current risk-reward to historical averages for similar situations.
5. Provide clear decision framework: when to hold, add, or exit.
6. Avoid anchoring to either bull or bear expert conclusions.""",
    "sector macro strategist": """Sector macro strategist providing global macro assessment and industry chain analysis for a specific sector. Follow these rules:
1. Evaluate monetary policy cycle impact on sector discount rates.
2. Map complete industry chain: upstream supply → midstream processing → downstream demand.
3. Quantify supply-demand balance with capacity utilization and inventory data.
4. Assess industry cycle position: expansion, peak, contraction, trough.
5. Identify policy catalysts and regulatory risks specific to the sector.
6. Link macro variables to sector-specific investment opportunities.""",
    "sector stock screener": """Sector stock screener identifying top investment candidates within a sector. Follow these rules:
1. Apply multi-factor scoring: fundamentals, technicals, sentiment, valuation.
2. Rank companies by risk-adjusted return potential.
3. Identify catalysts specific to each screened company.
4. Flag liquidity risks for small-cap names.
5. Cross-validate screening results against sector macro thesis.
6. Provide tiered recommendations: core holdings, satellite positions, watchlist.""",
    "sector risk auditor": """Sector risk auditor performing comprehensive risk assessment for sector investments. Follow these rules:
1. Identify sector-level systemic risks (policy, regulatory, cyclical).
2. Assess company-specific risks within the sector context.
3. Stress test portfolio under sector-specific adverse scenarios.
4. Evaluate correlation risks between recommended positions.
5. Define kill-switch triggers for sector thesis and individual positions.
6. Provide risk budget allocation across the recommended portfolio.""",
    "sector chief strategist": """Sector chief strategist providing final investment verdict for a sector. Follow these rules:
1. Synthesize all sector expert analyses into clear investment rating (overweight/underweight/neutral).
2. Provide time-framed outlook: 3-month, 6-month, 1-year, 2-year.
3. Recommend specific portfolio with position weights and entry timing.
4. Define scenario analysis: bull, base, bear cases with probabilities.
5. Arbitrate disagreements between sector experts with clear reasoning.
6. Include catalyst calendar and key risk monitoring milestones.""",
    "backtest agent": """Backtest agent performing historical quantitative backtesting on portfolio recommendations. Follow these rules:
1. Run rolling window backtests using at least 3 years of historical data.
2. Calculate key metrics: annualized return, Sharpe ratio, max drawdown, win rate.
3. Perform covariance-based portfolio optimization where applicable.
4. Compare backtested performance against benchmark indices.
5. Flag survivorship bias and look-ahead bias in backtest methodology.
6. Provide clear attribution analysis: which factors drove returns.""",
}

# Mapping from actual expert role names (lowercase) to genome keys
ROLE_TO_GENOME_MAP = {
    "deep research specialist": "deep research specialist",
    "technical analyst": "technical analyst",
    "fundamental analyst": "fundamental analyst",
    "chief audit officer": "chief audit officer",
    "sentiment analyst": "sentiment analyst",
    "bull researcher": "bull researcher",
    "bear researcher": "bear researcher",
    "professional reviewer": "professional reviewer",
    "soros-style financial philosopher": "soros-style financial philosopher",
    "value investing sage": "value investing sage",
    "contrarian strategist": "contrarian strategist",
    "risk manager": "risk manager",
    "chief strategist": "chief strategist",
    "serenity alpha analyst": "serenity alpha analyst",
    "macro hedge titan": "macro hedge titan",
    "growth visionary": "growth visionary",
    "aggressive risk analyst": "aggressive risk analyst",
    "conservative risk analyst": "conservative risk analyst",
    "neutral risk analyst": "neutral risk analyst",
    "sector macro strategist": "sector macro strategist",
    "sector stock screener": "sector stock screener",
    "sector risk auditor": "sector risk auditor",
    "sector chief strategist": "sector chief strategist",
    "backtest agent": "backtest agent",
    # Legacy aliases mapping to closest genome
    "technicals": "technical analyst",
    "financials": "fundamental analyst",
    "macro": "macro hedge titan",
}
POPULATION_SIZE = 3


class SimpleVectorMemory:
    """Lightweight vector memory using Qdrant + fastembed (no mem0 dependency)."""

    def __init__(self, qdrant_url: str, qdrant_path: str):
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance, PointStruct
        import uuid

        self._client_class = QdrantClient
        self._point_class = PointStruct
        self._uuid = uuid

        if qdrant_url:
            self.client = QdrantClient(url=qdrant_url, prefer_grpc=False)
        else:
            self.client = QdrantClient(path=qdrant_path)

        self.collection = "brain_memory"
        self._ensure_collection()

    def _ensure_collection(self):
        from qdrant_client.models import VectorParams, Distance
        try:
            self.client.get_collection(self.collection)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    def _embed(self, texts: list) -> list:
        """Simple hash-based embedding for offline environments."""
        import hashlib
        import numpy as np

        def text_to_vec(text: str, dim: int = 384) -> np.ndarray:
            words = text.lower().split()
            vec = np.zeros(dim)
            for i, word in enumerate(words):
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                idx = h % dim
                vec[idx] += 1.0 / (i + 1)
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 0 else vec

        return [text_to_vec(t) for t in texts]

    def add(self, text: str, user_id: str = "default", metadata: dict = None):
        embedding = self._embed([text])[0]
        if hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()
        point = self._point_class(
            id=str(self._uuid.uuid4()),
            vector=embedding,
            payload={"text": text, "user_id": user_id, **(metadata or {})}
        )
        self.client.upsert(collection_name=self.collection, points=[point])

    def search(self, query: str, user_id: str = "default", limit: int = 5, filters: dict = None) -> list:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        embedding = self._embed([query])[0]
        if hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()

        uid = user_id
        if filters and isinstance(filters, dict):
            uid = filters.get("user_id", user_id)

        query_filter = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=uid))])
        results = self.client.query_points(
            collection_name=self.collection,
            query=embedding,
            limit=limit,
            query_filter=query_filter
        )
        return [{"memory": r.payload.get("text", ""), "score": r.score} for r in results.points]


class BrainManager:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self._memory = None
        self._memory_init_failed = False
        self._gemini_client = None
        self._deepseek_client = None
        if self.gemini_key:
            os.environ["GOOGLE_API_KEY"] = self.gemini_key
        else:
            logger.info("BrainManager: GEMINI_API_KEY not found, will use DeepSeek for evolution.")

        self.state = self._load_genome_state()


    @property
    def memory(self):
        if self._memory is not None:
            return self._memory
        if self._memory_init_failed:
            return None
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("DISABLE_VECTOR_MEMORY", "").lower() == "true":
            self._memory_init_failed = True
            return None

        try:
            self._memory = SimpleVectorMemory(QDRANT_URL, QDRANT_PATH)
            logger.info("BrainManager: Vector memory initialized (Qdrant + fastembed)")
        except Exception as e:
            self._memory_init_failed = True
            logger.warning(f"BrainManager: Failed to init vector memory: {e}")
            return None
        return self._memory

    @property
    def gemini_client(self):
        if self._gemini_client is None and self.gemini_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.gemini_key)
            except Exception as e:
                logger.warning(f"BrainManager: Failed to initialize Gemini client: {e}")
        return self._gemini_client

    @property
    def deepseek_client(self):
        if self._deepseek_client is None and self.deepseek_key:
            try:
                import openai
                self._deepseek_client = openai.OpenAI(
                    api_key=self.deepseek_key,
                    base_url="https://api.deepseek.com"
                )
            except Exception as e:
                logger.warning(f"BrainManager: Failed to initialize DeepSeek client: {e}")
        return self._deepseek_client

    def get_brain_context(self, user_id: str, query: str = None, role: str = "global") -> dict:
        """
        Retrieves long-term memory facts and evolved system instructions for a specific role.
        """
        facts = []
        if self.memory and query:
            try:
                # Search with filters as required by newer Mem0 versions
                search_results = self.memory.search(query, filters={"user_id": user_id})
                
                # Mem0 2.0.0+ returns a dictionary with 'results' key
                if isinstance(search_results, dict) and "results" in search_results:
                    results_list = search_results["results"]
                else:
                    results_list = search_results
                    
                facts = []
                for res in results_list:
                    if "memory" in res:
                        facts.append(res["memory"])
                    elif "text" in res:
                        facts.append(res["text"])
            except Exception as e:
                logger.warning(f"BrainManager: Memory search failed: {e}")

        return {
            "facts": facts,
            "instructions": self._get_instructions_for_role(role)
        }

    def process_feedback(self, feedback_data: dict):
        """
        Updates global evolution and per-user memory based on feedback.
        """
        user_id = feedback_data.get("user_id", "anonymous")
        feedback_text = feedback_data.get("feedback", "")
        analysis_context = feedback_data.get("context", "") # What was being analyzed
        
        # 1. Update long-term memory (facts)
        if self.memory and feedback_text:
            try:
                self.memory.add(f"User feedback on {analysis_context}: {feedback_text}", user_id=user_id)
            except Exception as e:
                logger.warning(f"BrainManager: Failed to add memory: {e}")

        # 2. Update Global Evolution (EvolveR logic)
        if feedback_text:
            self._evolve_instructions(feedback_text, analysis_context)

    def _get_instructions_for_role(self, role: str) -> str:
        genome_key = ROLE_TO_GENOME_MAP.get(role, role)
        genome = self.state.genomes.get(genome_key, self.state.genomes.get("global"))
        if genome and genome.alpha:
            return genome.alpha.content
        return DEFAULT_GENOMES.get(genome_key, DEFAULT_GENOMES.get(role, DEFAULT_GENOMES["global"]))

    def get_evolved_instructions(self) -> Dict[str, Any]:
        """
        Public API to get current evolved instructions.
        """
        return {role: genome.alpha.content for role, genome in self.state.genomes.items() if genome.alpha}

    def get_evolution_history(self, role: str) -> List[Dict[str, Any]]:
        """
        Retrieves the history of genetic mutations for a role.
        """
        genome = self.state.genomes.get(role)
        if not genome:
            return []
        
        history = []
        for gene in sorted(genome.population, key=lambda g: g.created_at, reverse=True):
            history.append({
                "id": gene.id,
                "version": gene.version,
                "content": gene.content,
                "fitness": gene.fitness,
                "feedback_logs": gene.feedback_logs,
                "created_at": gene.created_at.isoformat(),
                "is_alpha": gene.id == genome.alpha_id
            })
        return history

    def _load_genome_state(self) -> EvolutionaryState:
        if not os.path.exists(EVOLVED_GENOME_FILE):
            return self._initialize_default_state()
        
        try:
            with open(EVOLVED_GENOME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Heuristic check for legacy format (flat dict of strings)
            if all(isinstance(v, str) for v in data.values()):
                logger.info("BrainManager: Legacy flat genome detected. Migrating...")
                return self._migrate_legacy_data(data)
            
            return EvolutionaryState.model_validate(data)
        except Exception as e:
            logger.warning(f"BrainManager: Failed to load genome state, using defaults: {e}")
            return self._initialize_default_state()

    def _initialize_default_state(self) -> EvolutionaryState:
        state = EvolutionaryState()
        for role, content in DEFAULT_GENOMES.items():
            gene = Gene(content=content)
            genome = Genome(role=role, population=[gene], alpha_id=gene.id)
            state.genomes[role] = genome
        return state

    def _migrate_legacy_data(self, legacy_data: dict) -> EvolutionaryState:
        state = EvolutionaryState()
        for role, content in legacy_data.items():
            gene = Gene(content=content)
            genome = Genome(role=role, population=[gene], alpha_id=gene.id)
            state.genomes[role] = genome
        self._save_genome_state(state)
        return state

    def _save_genome_state(self, state: EvolutionaryState):
        try:
            with open(EVOLVED_GENOME_FILE, "w", encoding="utf-8") as f:
                f.write(state.model_dump_json(indent=2))
        except Exception as e:
            logger.error(f"BrainManager: Failed to save genome state: {e}")

    def update_instructions(self, new_instructions: str, role: str = "global"):
        """
        Manually overwrite the alpha gene for a specific role.
        """
        if not new_instructions:
            raise ValueError("Instructions cannot be empty.")
        
        gene = Gene(content=new_instructions.strip())
        if role not in self.state.genomes:
            self.state.genomes[role] = Genome(role=role, population=[gene], alpha_id=gene.id)
        else:
            self.state.genomes[role].population.append(gene)
            self.state.genomes[role].alpha_id = gene.id
            # Trim if needed (manual updates don't necessarily need to follow population limits)
            if len(self.state.genomes[role].population) > POPULATION_SIZE:
                 self.state.genomes[role].population = self.state.genomes[role].population[-POPULATION_SIZE:]
        
        self._save_genome_state(self.state)
        logger.info(f"BrainManager: Instructions updated manually for role '{role}'.")


    def _evolve_instructions(self, feedback: str, context: str):
        # Determine role from context (simple heuristic)
        role = "global"
        ctx_lower = context.lower()
        if "tech" in ctx_lower or "chart" in ctx_lower:
            role = "technical analyst"
        elif "financial" in ctx_lower or "report" in ctx_lower or "fundamental" in ctx_lower:
            role = "fundamental analyst"
        elif "macro" in ctx_lower or "fed" in ctx_lower:
            role = "macro hedge titan"
        elif "risk" in ctx_lower:
            role = "risk manager"
        elif "sentiment" in ctx_lower or "情绪" in ctx_lower:
            role = "sentiment analyst"
        elif "bull" in ctx_lower or "看多" in ctx_lower:
            role = "bull researcher"
        elif "bear" in ctx_lower or "看空" in ctx_lower:
            role = "bear researcher"
        elif "strategy" in ctx_lower or "策略" in ctx_lower:
            role = "chief strategist"

        if role not in self.state.genomes:
            self.state.genomes[role] = Genome(role=role)
            # Add a base gene if empty
            base_content = DEFAULT_GENOMES.get(role, DEFAULT_GENOMES["global"])
            base_gene = Gene(content=base_content)
            self.state.genomes[role].population.append(base_gene)
            self.state.genomes[role].alpha_id = base_gene.id

        genome = self.state.genomes[role]
        
        # 1. Mutate (Generation of a new candidate)
        new_gene = self._mutate(genome, feedback)
        if new_gene:
            # Add to population
            genome.population.append(new_gene)
            # Trim population (FIFO)
            if len(genome.population) > POPULATION_SIZE:
                genome.population = genome.population[-POPULATION_SIZE:]
            
            # 2. Select (Re-evaluate winner)
            new_alpha_id = self._select(genome, feedback)
            if new_alpha_id:
                genome.alpha_id = new_alpha_id
                logger.info(f"BrainManager: Role '{role}' evolved. Alpha is now: {genome.alpha_id}")
            
            self._save_genome_state(self.state)

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM with DeepSeek (primary) or Gemini (fallback)."""
        # Try DeepSeek first
        if self.deepseek_client:
            try:
                model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
                response = self.deepseek_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.7
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"BrainManager: DeepSeek call failed: {e}")

        # Fallback to Gemini
        if self.gemini_client:
            try:
                model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"BrainManager: Gemini call failed: {e}")

        return None

    def _mutate(self, genome: Genome, feedback: str) -> Optional[Gene]:
        """Generate a new instruction variant based on alpha and feedback."""
        alpha_content = genome.alpha.content if genome.alpha else "No baseline available."

        prompt = f"""You are a prompt evolution engine for a quantitative trading AI.

Expert Role: {genome.role}
Current Best Instructions:
{alpha_content}

User Feedback:
"{feedback}"

Task: Improve the instructions by incorporating the feedback. Keep what works, fix what doesn't.
Return ONLY the improved instructions, no explanations."""
        try:
            mutated_content = self._call_llm(prompt)
            if mutated_content:
                new_gene = Gene(content=mutated_content, version=len(genome.population) + 1)
                new_gene.feedback_logs.append(feedback)
                return new_gene
        except Exception as e:
            logger.error(f"BrainManager: Mutation failed: {e}")
        return None

    def _select(self, genome: Genome, feedback: str) -> Optional[str]:
        """Select the best gene from the population based on feedback."""
        if not genome.population:
            return None

        gene_entries = "\n\n".join([
            f"[ID: {g.id}]\nContent:\n{g.content[:500]}"
            for g in genome.population
        ])

        prompt = f"""You are judging which set of instructions is best for an AI analyst.

Expert Role: {genome.role}

Candidate instruction sets:
{gene_entries}

Latest user feedback:
"{feedback}"

Return ONLY the ID of the best candidate (e.g., "abc123"). No explanation."""
        try:
            winning_id = self._call_llm(prompt)
            if winning_id:
                # Extract ID if wrapped in quotes or extra text
                winning_id = winning_id.strip().strip('"').strip("'").split()[0]
                if any(g.id == winning_id for g in genome.population):
                    return winning_id
                # Try partial match
                for g in genome.population:
                    if g.id.startswith(winning_id[:8]):
                        return g.id
                logger.warning(f"BrainManager: Model returned invalid ID: {winning_id}")
        except Exception as e:
            logger.error(f"BrainManager: Selection failed: {e}")
        return genome.alpha_id


# Global instance
brain_manager = BrainManager()
