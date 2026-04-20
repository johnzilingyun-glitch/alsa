import YahooFinance from 'yahoo-finance2';

/**
 * Unified Yahoo Finance Singleton
 * 
 * Ensures consistent configuration across the entire Node.js backend.
 * Uses default options for v3.x compatibility.
 */

const yf = new YahooFinance();

export { yf };
export default yf;
