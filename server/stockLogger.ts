import fs from 'fs';
import path from 'path';

const LOG_DIR = path.join(process.cwd(), 'logs');
const LOG_FILE = path.join(LOG_DIR, 'debug_records.log');

if (!fs.existsSync(LOG_DIR)) {
    fs.mkdirSync(LOG_DIR);
}

export function logDebug(type: string, data: any) {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        type,
        data: typeof data === 'object' ? JSON.stringify(data, null, 2) : data
    };

    const logString = `[${timestamp}] [${type.toUpperCase()}]\n${logEntry.data}\n${'-'.repeat(50)}\n`;
    
    // Console log for immediate visibility in terminal
    console.log(`[DEBUG_LOG] ${type.toUpperCase()}: ${typeof data === 'string' ? data : 'Object logged to file'}`);

    try {
        fs.appendFileSync(LOG_FILE, logString);
    } catch (error) {
        console.error('Failed to write to debug log file:', error);
    }
}

export function logError(error: any, context?: string) {
    const message = error instanceof Error ? error.stack || error.message : String(error);
    logDebug(`error${context ? `_${context}` : ''}`, message);
}
