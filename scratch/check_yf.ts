import YahooFinance from 'yahoo-finance2';
console.log('Type of default export:', typeof YahooFinance);
try {
  const instance = new YahooFinance();
  console.log('Successfully created instance. Method search type:', typeof instance.search);
  console.log('Static search method type:', typeof YahooFinance.search);
} catch (e) {
  console.log('Failed to create instance:', e.message);
}
