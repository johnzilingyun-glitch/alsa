import { Scenario, ExpectedValueOutcome } from "../types";

/**
 * Calculates the Expected Value (EV) price from a list of scenarios.
 * Standard Formula: Σ (Probability_i * Price_i)
 */
export function calculateExpectedValue(scenarios: Scenario[]): ExpectedValueOutcome {
  if (!scenarios || scenarios.length === 0) {
    return {
      expectedPrice: 0,
      calculationLogic: "No scenarios provided",
      confidenceInterval: "N/A"
    };
  }

  let totalWeight = 0;
  let weightedSum = 0;
  let minPrice = Infinity;
  let maxPrice = -Infinity;

  scenarios.forEach(s => {
    const price = parseFloat(s.targetPrice.replace(/[^0-9.]/g, ''));
    if (!isNaN(price)) {
      weightedSum += (s.probability / 100) * price;
      totalWeight += s.probability;
      if (price < minPrice) minPrice = price;
      if (price > maxPrice) maxPrice = price;
    }
  });

  // Normalize if total weight isn't 100% (though prompt mandates 100%)
  const expectedPrice = totalWeight > 0 ? parseFloat(weightedSum.toFixed(2)) : 0;
  
  return {
    expectedPrice,
    calculationLogic: `Σ(P_i * Price_i) = ${scenarios.map(s => `${s.probability}% * ${s.targetPrice}`).join(' + ')}`,
    confidenceInterval: `[${minPrice === Infinity ? 0 : minPrice}, ${maxPrice === -Infinity ? 0 : maxPrice}]`
  };
}
