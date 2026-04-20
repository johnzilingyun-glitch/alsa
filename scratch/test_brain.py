import os
import sys
from dotenv import load_dotenv

# Add the project root to sys.path to allow imports
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(root_dir, "python_service"))

from app.services.brain_manager import brain_manager

def test_evolution():
    print("Testing BrainManager evolution...")
    feedback = "The technical analysis is too focused on short-term noise. Need more emphasis on long-term trend lines."
    context = "Technical analysis for 600519"
    
    try:
        brain_manager.process_feedback({"feedback": feedback, "context": context})
        print("Evolution call successful.")
        
        genome = brain_manager._load_genome()
        print(f"Updated genome for technicals: {genome.get('technicals')}")
    except Exception as e:
        print(f"Evolution call failed: {e}")

if __name__ == "__main__":
    test_evolution()
