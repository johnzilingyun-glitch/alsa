const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  page.on('console', msg => {
    console.log(`CONSOLE [${msg.type()}]: ${msg.text()}`);
  });

  page.on('pageerror', exception => {
    console.log(`UNCAUGHT EXCEPTION: ${exception}`);
  });

  await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 10000 }).catch(e => console.log('Navigation Error:', e));
  
  const content = await page.content();
  fs.writeFileSync('screenshot.html', content);
  
  await browser.close();
})();
