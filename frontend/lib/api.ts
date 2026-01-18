/**
 * API Call Wrapper
 */
import { AnalysisRequest, AnalysisResponse } from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export async function analyzeStock(params: AnalysisRequest): Promise<AnalysisResponse> {
  const response = await fetch(`${API_URL}/api/v1/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}
