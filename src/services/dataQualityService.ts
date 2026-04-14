import { StockInfo, DataQuality } from "../types";

const STALENESS_THRESHOLD_MS = 4 * 60 * 60 * 1000; // 4 hours

export function calculateQualityScore(info: StockInfo): DataQuality {
  let score = 100;
  const missingFields: string[] = [];

  // Check critical fields
  if (!info.price || info.price <= 0) {
    score -= 30;
    missingFields.push("Price");
  }
  
  if (info.previousClose === undefined || info.previousClose === 0) {
    score -= 10;
    missingFields.push("Previous Close");
  }

  // Check source priority
  let sourcePriority: DataQuality["sourcePriority"] = "Official API";
  if (info.dataSource === "Google Search" || !info.dataSource) {
    sourcePriority = "Search/Scraped";
    score -= 10;
  } else if (info.dataSource === "AI Inference") {
    sourcePriority = "AI Estimated";
    score -= 25;
  }

  // Check forstaleness
  const lastUpdatedDate = new Date(info.lastUpdated);
  const now = new Date();
  const diff = now.getTime() - lastUpdatedDate.getTime();
  const isStale = diff > STALENESS_THRESHOLD_MS;

  if (isStale) {
    score -= 15;
  }

  return {
    score: Math.max(0, score),
    lastSync: info.lastUpdated,
    sourcePriority,
    isStale,
    missingFields
  };
}

export function getQualityLabel(score: number): { label: string; color: string } {
  if (score >= 90) return { label: "high", color: "text-[#34C759]" };
  if (score >= 70) return { label: "reliable", color: "text-blue-400" };
  if (score >= 50) return { label: "moderate", color: "text-amber-400" };
  return { label: "low", color: "text-rose-400" };
}
