const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 10000 }).catch(e => console.log('Navigation Error:', e));
  
  const errorText = await page.evaluate(() => {
    const overlay = document.querySelector('vite-error-overlay');
    if (overlay && overlay.shadowRoot) {
      return overlay.shadowRoot.textContent;
    }
    return 'No error overlay found';
  });
  
  console.log('VITE ERROR:', errorText);
  await browser.close();
})();
