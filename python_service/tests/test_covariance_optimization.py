import pandas as pd
import numpy as np

# We'll just test the core covariance logic that was added to the discussion_service.py.
# To keep it isolated from the complex LLM and agent orchestration, we'll extract the exact math used.
def compute_mvo(returns_df):
    cov_matrix = returns_df.cov()
    corr_matrix = returns_df.corr()
    
    cov = cov_matrix.values
    n_assets = cov.shape[0]
    ones = np.ones(n_assets)
    
    high_corr_warns = []
    high_corr_threshold = 0.75
    for i in range(n_assets):
        for j in range(i + 1, n_assets):
            r_val = corr_matrix.iloc[i, j]
            if r_val > high_corr_threshold:
                high_corr_warns.append((returns_df.columns[i], returns_df.columns[j], r_val))
                
    cov_reg = cov + np.eye(n_assets) * 1e-6
    inv_cov = np.linalg.inv(cov_reg)
    raw_w = np.dot(inv_cov, ones)
    
    w_clipped = np.clip(raw_w, 0, None)
    if np.sum(w_clipped) > 0:
        w = w_clipped / np.sum(w_clipped)
    else:
        w = ones / n_assets
        
    return {returns_df.columns[k]: float(w[k]) for k in range(n_assets)}, high_corr_warns

def test_covariance_matrix_optimization():
    # 1. Create artificial returns where two assets are highly correlated, and one is uncorrelated
    dates = pd.date_range("2023-01-01", periods=100)
    
    # Asset A and B are identical (correlation = 1)
    # Asset C is completely independent
    np.random.seed(42)
    a_returns = np.random.normal(0.001, 0.02, 100)
    b_returns = a_returns + np.random.normal(0, 0.001, 100) # highly correlated with A
    c_returns = np.random.normal(0.001, 0.02, 100)
    
    returns_df = pd.DataFrame({
        "A": a_returns,
        "B": b_returns,
        "C": c_returns
    }, index=dates)
    
    weights, warns = compute_mvo(returns_df)
    
    # Verify weights are long-only and sum to 1
    assert all(w >= 0 for w in weights.values())
    assert np.isclose(sum(weights.values()), 1.0)
    
    # Verify high correlation warning for A and B
    assert len(warns) == 1
    assert warns[0][0] == "A"
    assert warns[0][1] == "B"
    assert warns[0][2] > 0.9  # Should be close to 1.0
