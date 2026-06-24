const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  page.on('response', response => {
    if (response.status() >= 400) {
      console.log(`HTTP ${response.status()} - ${response.url()}`);
    }
  });

  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 5000 }).catch(e => {});
  await page.waitForTimeout(2000); // Wait a bit for requests to finish
  
  await browser.close();
})();
