import sys
import os
import unittest
import json
from unittest.mock import MagicMock, patch

# Add the app directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.brain_manager import BrainManager
from app.services.gep_models import EvolutionaryState, Genome, Gene

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

    @patch("google.genai.Client")
    def test_evolution_cycle(self, mock_genai):
        """Verify the full evolution cycle: mutate then select."""
        # Mock mutation response
        mock_mutation_resp = MagicMock()
        mock_mutation_resp.text = "Mutated instructions"
        
        # Mock selection response (return the ID of the new gene)
        # Note: We can't easily know the ID beforehand, so we'll mock the selection to return a specific string
        # and then verify that _select handles it.
        
        with patch.object(BrainManager, "model") as mock_model:
            # We will mock the generate_content calls sequentially
            mock_model.models.generate_content.side_effect = [
                mock_mutation_resp, # for _mutate
                MagicMock(text="placeholder_id") # for _select
            ]
            
            # Setup a genome
            role = "technicals"
            feedback = "Better volume analysis needed."
            context = "technical analysis of AAPL"
            
            # Run evolution
            # We'll intercept the selection to return the newly created gene's ID
            original_mutate = self.manager._mutate
            created_gene_id = None
            
            def mocked_mutate(genome, fb):
                gene = original_mutate(genome, fb)
                nonlocal created_gene_id
                created_gene_id = gene.id
                return gene
            
            with patch.object(self.manager, "_mutate", side_effect=mocked_mutate):
                with patch.object(self.manager, "_select", side_effect=lambda g, fb: created_gene_id):
                    self.manager._evolve_instructions(feedback, context)
            
            # Verify alpha was updated
            genome = self.manager.state.genomes[role]
            self.assertEqual(genome.alpha_id, created_gene_id)
            self.assertEqual(genome.alpha.content, "Mutated instructions")
            self.assertIn(feedback, genome.alpha.feedback_logs)

if __name__ == "__main__":
    unittest.main()
