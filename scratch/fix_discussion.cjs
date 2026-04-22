const fs = require('fs');
const path = 'd:/zily/alsa/alsa/src/services/discussionService.ts';
let content = fs.readFileSync(path, 'utf8');

const startTag = 'const invokeExpert = async (inputPrompt: string, isFallback = false): Promise<any> => {';
const nextBlock = '      try {';

const startIndex = content.indexOf(startTag);
if (startIndex === -1) {
    console.error('Start tag not found');
    process.exit(1);
}

const nextBlockIndex = content.indexOf(nextBlock, startIndex);
if (nextBlockIndex === -1) {
    console.error('Next block not found');
    process.exit(1);
}

// Find the first 'catch (e) {' block after start
const catchIndex = content.indexOf('catch (e) {', startIndex);
const closingBraceIndex = content.indexOf('};', catchIndex);

if (closingBraceIndex === -1 || closingBraceIndex > nextBlockIndex) {
    console.error('Closing brace for function not found or out of bounds');
    process.exit(1);
}

const newBody = `
        const hasTools = !!tools;
        // Automated model fallback (Pro to Flash) to handle API quota issues
        const currentModel = isFallback ? "gemini-3.1-flash-lite-preview" : model;
        const currentTools = isFallback ? DUCKDUCKGO_TOOLS : tools;

        try {
          return await generateAndParseJsonWithRetry<ExpertAnalysisResult>(ai, {
            model: currentModel,
            contents: inputPrompt,
            config: { 
              responseMimeType: (hasTools || isFallback) ? undefined : "application/json",
              maxOutputTokens: 2048,
              tools: currentTools
            },
          });
        } catch (e) {
          console.warn(\`[DiscussionService] Expert \${role} failed (isFallback=\${isFallback}), error:\`, e);
          if (!isFallback) {
            console.info(\`[DiscussionService] Triggering automated recovery to Flash for \${role}...\`);
            return await invokeExpert(inputPrompt, true);
          }
          throw e; // Final failure after fallback
        }
      `;

const finalContent = content.substring(0, startIndex + startTag.length) + newBody + content.substring(closingBraceIndex);
fs.writeFileSync(path, finalContent, 'utf8');
console.log('Successfully updated discussionService.ts');
