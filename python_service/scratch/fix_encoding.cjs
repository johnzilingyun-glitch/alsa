const fs = require('fs');
const path = 'd:/zily/alsa/alsa/src/services/discussionService.ts';
let content = fs.readFileSync(path, 'utf8');

// Use regex to catch those trailing weird characters after the quotes
content = content.replace(/无法进行有效技术面形态分析[^"]*"/g, '无法进行有效技术面形态分析。"');
content = content.replace(/建议等待财报披露[^"]*"/g, '建议等待财报披露。"');
content = content.replace(/建议关注行业平均收益率[^"]*"/g, '建议关注行业平均收益率。"');

fs.writeFileSync(path, content, 'utf8');
console.log('Fixed encoding in discussionService.ts');
