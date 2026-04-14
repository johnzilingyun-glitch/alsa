import type { AgentRole, OrchestratorConfig } from '../../types';

type AssetType = OrchestratorConfig['assetType'];

/**
 * Returns expert roles that should be skipped for a given asset type.
 * ETFs and indices don't need deep research or fundamental analysis.
 */
export function getSkipRoles(assetType: AssetType): AgentRole[] {
  switch (assetType) {
    case 'etf':
    case 'index':
      return ['Deep Research Specialist', 'Fundamental Analyst'];
    case 'bond':
      return ['Technical Analyst'];
    default:
      return [];
  }
}
