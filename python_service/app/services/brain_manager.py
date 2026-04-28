import os
import json
from jinja2 import Template
from mem0 import Memory
from dotenv import load_dotenv
from google import genai
from typing import Optional, List, Dict, Any
from .gep_models import EvolutionaryState, Genome, Gene


# Ensure we load .env from the root directory (4 levels up from this file)
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

# Configuration for Mem0 and EvolveR
BRAIN_DATA_DIR = os.path.join(root_dir, "data", "brain")
EVOLVED_GENOME_FILE = os.path.join(BRAIN_DATA_DIR, "evolved_genome.json")
QDRANT_PATH = os.path.join(BRAIN_DATA_DIR, "qdrant_db")

os.makedirs(BRAIN_DATA_DIR, exist_ok=True)

DEFAULT_GENOMES = {
    "global": "- Always prioritize quantitative data over qualitative descriptions.\n- Cross-verify stock prices with commodity pivots if relevant.\n- Maintain an institutional, objective tone.",
    "technicals": "- Prioritize high-conviction breakout patterns.\n- Validate volume confirmation for all trend transitions.",
    "financials": "- Focus on revenue quality and sustainable margins.\n- Cross-reference debt maturity schedules for risk assessment.",
    "macro": "- Trace interest rate impacts through specific sector sensitivities.\n- Evaluate geopolitical risks on commodity supply chains."
}
POPULATION_SIZE = 3


class BrainManager:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._memory = None
        self._model = None
        if self.api_key:
            os.environ["GOOGLE_API_KEY"] = self.api_key
        else:
            print("WARNING: GEMINI_API_KEY not found in environment.")
        
        self.state = self._load_genome_state()


    @property
    def memory(self):
        if self._memory is None:
            mem0_config = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {"path": QDRANT_PATH}
                },
                "llm": {
                    "provider": "gemini" if self.api_key else "openai",
                    "config": {
                        "model": "gemini-3.1-flash-lite-preview" if self.api_key else "deepseek-v4-pro",
                        "api_key": self.api_key or os.getenv("DEEPSEEK_API_KEY"),
                        "base_url": None if self.api_key else "https://api.deepseek.com"
                    }
                },
                "embedder": {
                    "provider": "gemini" if self.api_key else "fastembed", 
                    "config": {"model": "models/gemini-embedding-2" if self.api_key else "BAAI/bge-small-en-v1.5", "api_key": self.api_key}
                }
            }
            try:
                self._memory = Memory.from_config(mem0_config)
                print("BrainManager: Mem0 initialized successfully (lazy).")
            except Exception as e:
                print(f"BrainManager: Failed to initialize Mem0: {e}")
                return None
        return self._memory

    @property
    def model(self):
        if self._model is None:
            try:
                self._model = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"BrainManager: Failed to initialize Gemini client: {e}")
        return self._model

    def get_brain_context(self, user_id: str, query: str = None, role: str = "global") -> dict:
        """
        Retrieves long-term memory facts and evolved system instructions for a specific role.
        """
        facts = []
        if self.memory and query:
            try:
                # Search with filters as required by newer Mem0 versions
                search_results = self.memory.search(query, filters={"user_id": user_id})
                facts = [res["text"] for res in search_results]
            except Exception as e:
                print(f"BrainManager: Memory search failed: {e}")

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
                print(f"BrainManager: Failed to add memory: {e}")

        # 2. Update Global Evolution (EvolveR logic)
        if feedback_text:
            self._evolve_instructions(feedback_text, analysis_context)

    def _get_instructions_for_role(self, role: str) -> str:
        genome = self.state.genomes.get(role, self.state.genomes.get("global"))
        if genome and genome.alpha:
            return genome.alpha.content
        return DEFAULT_GENOMES.get(role, DEFAULT_GENOMES["global"])

    def get_evolved_instructions(self) -> Dict[str, Any]:
        """
        Public API to get current evolved instructions.
        """
        return {role: genome.alpha.content for role, genome in self.state.genomes.items() if genome.alpha}

    def _load_genome_state(self) -> EvolutionaryState:
        if not os.path.exists(EVOLVED_GENOME_FILE):
            return self._initialize_default_state()
        
        try:
            with open(EVOLVED_GENOME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Heuristic check for legacy format (flat dict of strings)
            if all(isinstance(v, str) for v in data.values()):
                print("BrainManager: Legacy flat genome detected. Migrating...")
                return self._migrate_legacy_data(data)
            
            return EvolutionaryState.model_validate(data)
        except Exception as e:
            print(f"BrainManager: Failed to load genome state, using defaults: {e}")
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
            print(f"BrainManager: Failed to save genome state: {e}")

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
        print(f"BrainManager: Instructions updated manually for role '{role}'.")


    def _evolve_instructions(self, feedback: str, context: str):
        # Determine role from context (simple heuristic)
        role = "global"
        ctx_lower = context.lower()
        if "tech" in ctx_lower or "chart" in ctx_lower:
            role = "technicals"
        elif "financial" in ctx_lower or "report" in ctx_lower or "fundamental" in ctx_lower:
            role = "financials"
        elif "macro" in ctx_lower or "fed" in ctx_lower:
            role = "macro"

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
                print(f"BrainManager: Role '{role}' evolved. Alpha is now: {genome.alpha_id}")
            
            self._save_genome_state(self.state)

    def _mutate(self, genome: Genome, feedback: str) -> Optional[Gene]:
        """
        Uses gemini-3.1-pro-preview to generate a new instruction variant based on alpha.
        """
        alpha_content = genome.alpha.content if genome.alpha else "No baseline available."
        
        prompt = f"""
        [GEP OPERATOR: MUTATE]
        Expert Role: {genome.role}
        Current Alpha Gene (Baseline Instructions):
        {alpha_content}

        Environmental Feedback:
        "{feedback}"

        Task: Apply a 'Directed Mutation' to create an improved instruction variant. 
        Focus on resolving the specific issues mentioned in the feedback while preserving successful historical patterns.
        
        Return ONLY the updated, comprehensive list of instructions.
        """
        try:
            response = self.model.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=prompt
            )
            mutated_content = response.text.strip()
            if mutated_content:
                new_gene = Gene(content=mutated_content, version=len(genome.population) + 1)
                new_gene.feedback_logs.append(feedback)
                return new_gene
        except Exception as e:
            print(f"BrainManager: Mutation failed: {e}")
        return None

    def _select(self, genome: Genome, feedback: str) -> Optional[str]:
        """
        Uses gemini-3.1-pro-preview as a critic to select the best gene in the population.
        """
        if not genome.population:
            return None
        
        gene_entries = "\n\n".join([f"ID: {g.id}\nVersion: {g.version}\nContent:\n{g.content}" for g in genome.population])
        
        prompt = f"""
        [GEP OPERATOR: SELECT]
        Expert Role: {genome.role}
        Total Population (Variants):
        {gene_entries}

        Latest Environmental Feedback:
        "{feedback}"

        Task: Critique the population. Identify which Gene ID best accommodates the latest feedback and provides the highest quality analysis instructions for this role.
        
        Return ONLY the winning Gene ID.
        """
        try:
            response = self.model.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=prompt
            )
            winning_id = response.text.strip()
            # Basic validation that it's a valid ID in our population
            if any(g.id == winning_id for g in genome.population):
                return winning_id
            else:
                print(f"BrainManager: Model returned invalid winning ID: {winning_id}")
        except Exception as e:
            print(f"BrainManager: Selection failed: {e}")
        return genome.alpha_id


# Global instance
brain_manager = BrainManager()
