import pytest

if __name__ == "__main__":
    result_path = "/home/ubuntu/work/alsa/python_service/scratch/poisoning_result.txt"
    # Run pytest and write output to result_path
    with open(result_path, "w") as f:
        f.write("Running tests...\n")
    
    # Run pytest.main
    exit_code = pytest.main(["tests/test_prompt_poisoning.py", "-v"])
    
    with open(result_path, "a") as f:
        f.write(f"\nExit code: {exit_code}\n")
    print(f"Done with exit code: {exit_code}")
