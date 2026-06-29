import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add the app directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.brain_manager import BrainManager, DEFAULT_GENOMES, ROLE_TO_GENOME_MAP
from app.services.gep_models import EvolutionaryState, Genome


class TestGEP(unittest.TestCase):
    def setUp(self):
        self.manager = BrainManager()

    def test_initialization(self):
        """Verify that BrainManager initializes with default genomes structured as GEP models."""
        state = self.manager.state
        self.assertIsInstance(state, EvolutionaryState)
        self.assertIn("global", state.genomes)
        self.assertIsInstance(state.genomes["global"], Genome)
        self.assertTrue(len(state.genomes["global"].population) > 0)
        self.assertIsNotNone(state.genomes["global"].alpha)

    def test_legacy_migration(self):
        """Verify that legacy flat JSON is correctly migrated to structured models."""
        legacy_data = {
            "global": "legacy global instructions",
            "technicals": "legacy technicals"
        }
        migrated_state = self.manager._migrate_legacy_data(legacy_data)
        self.assertIn("global", migrated_state.genomes)
        self.assertEqual(migrated_state.genomes["global"].alpha.content, "legacy global instructions")
        self.assertEqual(len(migrated_state.genomes["global"].population), 1)

    def test_evolution_cycle(self):
        """Verify the full evolution cycle: mutate then select."""
        role = "technical analyst"
        feedback = "Better volume analysis needed."
        context = "technical analysis of AAPL"

        original_mutate = self.manager._mutate
        created_gene_id = None

        def mocked_mutate(genome, fb):
            gene = original_mutate(genome, fb)
            nonlocal created_gene_id
            created_gene_id = gene.id
            return gene

        with patch.object(self.manager, "_call_llm", return_value="Mutated instructions"):
            with patch.object(self.manager, "_mutate", side_effect=mocked_mutate):
                with patch.object(self.manager, "_select", side_effect=lambda g, fb: created_gene_id):
                    self.manager._evolve_instructions(feedback, context)

        genome = self.manager.state.genomes[role]
        self.assertEqual(genome.alpha_id, created_gene_id)
        self.assertEqual(genome.alpha.content, "Mutated instructions")
        self.assertIn(feedback, genome.alpha.feedback_logs)


class TestRoleMapping(unittest.TestCase):
    """Tests for the expanded role mapping and evolution mechanism."""

    def setUp(self):
        self.manager = BrainManager()

    def test_default_genomes_covers_all_expert_roles(self):
        """DEFAULT_GENOMES must include every role used in discussion topologies."""
        from app.services.discussion_service import (
            DEEP_TOPOLOGY, STANDARD_TOPOLOGY, QUICK_TOPOLOGY, SECTOR_TOPOLOGY,
        )

        all_topology_roles = set()
        for topo in [DEEP_TOPOLOGY, STANDARD_TOPOLOGY, QUICK_TOPOLOGY, SECTOR_TOPOLOGY]:
            for round_def in topo:
                for expert in round_def["experts"]:
                    all_topology_roles.add(expert.lower())

        missing = all_topology_roles - set(DEFAULT_GENOMES.keys())
        self.assertEqual(missing, set(), f"DEFAULT_GENOMES missing roles: {missing}")

    def test_role_to_genome_map_covers_all_defaults(self):
        """Every key in DEFAULT_GENOMES should have a mapping entry (or be self-mapping)."""
        for role in DEFAULT_GENOMES:
            mapped = ROLE_TO_GENOME_MAP.get(role, role)
            self.assertIn(mapped, DEFAULT_GENOMES, f"Role '{role}' maps to '{mapped}' which is not in DEFAULT_GENOMES")

    def test_legacy_aliases_map_correctly(self):
        """Legacy role names (technicals, financials, macro) map to new names."""
        self.assertEqual(ROLE_TO_GENOME_MAP["technicals"], "technical analyst")
        self.assertEqual(ROLE_TO_GENOME_MAP["financials"], "fundamental analyst")
        self.assertEqual(ROLE_TO_GENOME_MAP["macro"], "macro hedge titan")

    def test_get_brain_context_returns_role_specific_instructions(self):
        """get_brain_context should return role-specific instructions, not global fallback."""
        test_roles = [
            "technical analyst",
            "fundamental analyst",
            "deep research specialist",
            "risk manager",
            "chief strategist",
            "bull researcher",
            "bear researcher",
            "sentiment analyst",
            "serenity alpha analyst",
            "contrarian strategist",
        ]
        for role in test_roles:
            ctx = self.manager.get_brain_context("test_user", query="AAPL Apple", role=role)
            instructions = ctx["instructions"]
            self.assertIsNotNone(instructions, f"Instructions should not be None for role '{role}'")
            self.assertNotEqual(
                instructions, DEFAULT_GENOMES["global"],
                f"Role '{role}' should NOT fall back to global instructions"
            )

    def test_get_brain_context_legacy_alias(self):
        """Legacy role names should resolve to the correct genome via mapping."""
        ctx_legacy = self.manager.get_brain_context("test_user", query="AAPL", role="technicals")
        ctx_new = self.manager.get_brain_context("test_user", query="AAPL", role="technical analyst")
        self.assertEqual(ctx_legacy["instructions"], ctx_new["instructions"])

    def test_get_brain_context_unknown_role_falls_back_to_global(self):
        """Truly unknown roles should gracefully fall back to global."""
        ctx = self.manager.get_brain_context("test_user", query="AAPL", role="nonexistent_role_xyz")
        # Should return non-empty instructions (either from evolved genome or DEFAULT_GENOMES)
        self.assertIsNotNone(ctx["instructions"])
        self.assertIsInstance(ctx["instructions"], str)
        self.assertGreater(len(ctx["instructions"]), 0)

    def test_evolve_instructions_routes_to_correct_role(self):
        """_evolve_instructions should route context keywords to the correct genome."""
        test_cases = [
            ("technical analysis of AAPL", "technical analyst"),
            ("fundamental report on TSLA", "fundamental analyst"),
            ("macro outlook for Fed meeting", "macro hedge titan"),
            ("risk assessment of portfolio", "risk manager"),
            ("sentiment analysis of NVDA", "sentiment analyst"),
            ("bull case for AMZN", "bull researcher"),
            ("bear case for META", "bear researcher"),
            ("strategy recommendation for GOOG", "chief strategist"),
        ]

        original_mutate = self.manager._mutate
        for context, expected_role in test_cases:
            captured_role = None

            def make_mock(expected):
                def mock_select(genome, fb):
                    nonlocal captured_role
                    captured_role = genome.role
                    return genome.alpha_id
                return mock_select

            with patch.object(self.manager, "_call_llm", return_value="evolved"):
                with patch.object(self.manager, "_select", side_effect=make_mock(expected_role)):
                    self.manager._evolve_instructions("test feedback", context)

            self.assertEqual(
                captured_role, expected_role,
                f"Context '{context}' should route to role '{expected_role}', got '{captured_role}'"
            )

    def test_evolution_cycle_increases_population(self):
        """Each evolution cycle should add a new gene to the population."""
        role = "risk manager"
        feedback = "Need better VaR calculation"
        context = "risk assessment of portfolio"

        with patch.object(self.manager, "_call_llm", return_value="improved risk instructions"):
            self.manager._evolve_instructions(feedback, context)

        genome = self.manager.state.genomes[role]
        self.assertGreaterEqual(len(genome.population), 2, "Population should have grown after evolution")

    def test_population_trimmed_to_max_size(self):
        """Population should not exceed POPULATION_SIZE after many evolutions."""
        from app.services.brain_manager import POPULATION_SIZE
        role = "technical analyst"

        with patch.object(self.manager, "_call_llm", return_value="mutated"):
            for i in range(10):
                self.manager._evolve_instructions(f"feedback {i}", "technical analysis")

        genome = self.manager.state.genomes[role]
        self.assertLessEqual(
            len(genome.population), POPULATION_SIZE,
            f"Population should be capped at {POPULATION_SIZE}"
        )

    def test_get_evolved_instructions_returns_all_roles(self):
        """get_evolved_instructions should return instructions for all roles with alpha genes."""
        evolved = self.manager.get_evolved_instructions()
        self.assertIsInstance(evolved, dict)
        self.assertIn("global", evolved)
        self.assertIn("technical analyst", evolved)
        self.assertIn("fundamental analyst", evolved)
        self.assertIn("risk manager", evolved)
        for role, content in evolved.items():
            self.assertIsInstance(content, str)
            self.assertGreater(len(content), 0, f"Instructions for '{role}' should not be empty")


if __name__ == "__main__":
    unittest.main()
