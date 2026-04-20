/**
 * BrainService: Handles interaction with the Python-based Memory (Mem0) 
 * and Evolution (EvolveR) engine.
 */

export interface BrainContext {
  facts: string[];
  instructions: string;
}

export async function getBrainContext(symbol: string, userId: string = "default_user"): Promise<BrainContext> {
  try {
    const response = await fetch(`/api/brain/context?user_id=${userId}&query=${encodeURIComponent(symbol)}`);
    if (!response.ok) {
        return { facts: [], instructions: "" };
    }
    const result = await response.json();
    return result.success ? result.data : { facts: [], instructions: "" };
  } catch (error) {
    console.error("BrainService: Failed to fetch context", error);
    return { facts: [], instructions: "" };
  }
}

export async function submitBrainFeedback(userId: string, feedback: string, context: string): Promise<boolean> {
  try {
    const response = await fetch('/api/brain/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, feedback, context }),
    });
    const result = await response.json();
    return !!result.success;
  } catch (error) {
    console.error("BrainService: Failed to submit feedback", error);
    return false;
  }
}
