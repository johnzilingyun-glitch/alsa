async function testWatchlistDelete() {
  const symbol = '600519'; // Kweichow Moutai
  const market = 'A-Share';
  console.log(`Testing watchlist deletion of symbol: ${symbol} (${market})`);
  
  try {
    const response = await fetch(`http://localhost:3000/api/watchlist/${symbol}?market=${market}`, {
      method: 'DELETE'
    });
    
    // Note: The Python backend might return 204 No Content or a JSON
    console.log('Response Status:', response.status);
    if (response.status !== 204) {
      const result = await response.json().catch(() => ({ msg: 'No JSON body' }));
      console.log('Result:', result);
    } else {
      console.log('Result: Success (No Content)');
    }
  } catch (err) {
    console.error('Fetch error:', err);
  }
}

testWatchlistDelete();
