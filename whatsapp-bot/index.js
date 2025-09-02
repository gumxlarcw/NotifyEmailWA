// index.js (di dalam folder whatsapp-bot)
let isReady = false;

const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const express = require('express');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');
const multer = require('multer');

// === PATHS ===
const READY_FLAG = path.resolve(__dirname, './wa_ready.flag');
const UPLOAD_DIR = path.resolve(__dirname, './uploads');
const SESSION_DIR = path.resolve(__dirname, './session');

// --- util: log ke file -------------------------------------------------------
function writeLog(message) {
  try {
    const logDir = path.resolve(__dirname, './logs');
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    const logFile = path.join(logDir, 'history.log');
    const timeStamp = new Date().toISOString();
    const logMessage = `[${timeStamp}] ${message}\n`;
    fs.appendFileSync(logFile, logMessage);
  } catch (e) {
    console.error('Failed to write log:', e);
  }
}

// --- util: flag file ---------------------------------------------------------
function setFlagReady() {
  try {
    fs.writeFileSync(READY_FLAG, new Date().toISOString());
  } catch (e) {
    writeLog('Failed to set READY_FLAG: ' + (e?.message || String(e)));
  }
}

function clearFlag() {
  try {
    if (fs.existsSync(READY_FLAG)) fs.unlinkSync(READY_FLAG);
  } catch (e) {
    writeLog('Failed to clear READY_FLAG: ' + (e?.message || String(e)));
  }
}

// --- startup hygiene ---------------------------------------------------------
clearFlag(); // pastikan flag bersih saat boot
try {
  if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });
} catch (e) {
  writeLog('Failed to ensure uploads dir: ' + (e?.message || String(e)));
}
try {
  if (!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR, { recursive: true });
} catch (e) {
  writeLog('Failed to ensure session dir: ' + (e?.message || String(e)));
}

// --- WA client ---------------------------------------------------------------
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_DIR }),          // absolut -> tahan CWD berubah
  puppeteer: { args: ['--no-sandbox', '--disable-setuid-sandbox'] },
  webVersionCache: { type: 'none' }                                // kunci fix stabilitas
});

// QR Code untuk login
client.on('qr', (qr) => {
  try {
    qrcode.generate(qr, { small: true });
  } catch (e) {
    writeLog('Failed to render QR: ' + (e?.message || String(e)));
  }
  // Belum ready: pastikan flag bersih
  isReady = false;
  clearFlag();
  writeLog('📷 QR generated (waiting for scan)');
});

// Loading screen (opsional, bagus untuk debugging)
client.on('loading_screen', (percent, msg) => {
  writeLog(`⌛ Loading ${percent}%: ${msg}`);
});

// Siap
client.on('ready', async () => {
  isReady = true;
  setFlagReady();
  const readyMsg = '✅ WhatsApp Web.js is ready!';
  console.log(readyMsg);
  writeLog(readyMsg);
});

// Perubahan state (opsional)
client.on('change_state', (state) => {
  writeLog('🔀 State changed: ' + state);
});

// Putus koneksi
client.on('disconnected', (reason) => {
  isReady = false;
  clearFlag();
  writeLog('❌ Disconnected: ' + (reason || 'unknown'));
});

// Auth failure
client.on('auth_failure', (msg) => {
  isReady = false;
  clearFlag();
  writeLog('❌ Auth failure: ' + (msg || 'unknown'));
});

// Error global (pakai precedence aman)
client.on('error', (err) => {
  writeLog('❌ Client error: ' + (err?.stack || err?.message || String(err)));
});

// Inisialisasi
client.initialize();

// --- contoh handler pesan sederhana -----------------------------------------
client.on('message', async (msg) => {
  try {
    if (msg.body === '!id') {
      const chat = await msg.getChat();
      if (chat.isGroup) {
        await msg.reply(`🆔 *Group ID:* ${chat.id._serialized}`);
      } else {
        await msg.reply(`🆔 *Chat ID:* ${chat.id._serialized}`);
      }
      writeLog(`🆔 ID requested by ${msg.from}: ${chat.id._serialized}`);
    }
  } catch (e) {
    writeLog('❌ Error in message handler: ' + (e?.message || String(e)));
  }
});

// --- Express API -------------------------------------------------------------
const app = express();
app.use(express.json());

// health/status endpoint supaya BAT/monitor bisa cek
app.get('/status', (req, res) => {
  res.json({ ready: isReady });
});

// kirim teks
app.post('/send', async (req, res) => {
  if (!isReady) {
    writeLog('❌ Client not ready. Message not sent.');
    return res.status(503).send('❌ WhatsApp client not ready yet');
  }

  const { number, chatId, message } = req.body || {};
  if (!message) {
    writeLog('❌ Missing message in request');
    return res.status(400).send('❌ Missing message');
  }

  let targetId = '';
  if (chatId) {
    targetId = chatId;
  } else if (number) {
    targetId = number.includes('@g.us') ? number : number + '@c.us';
  } else {
    writeLog('❌ Missing target number or chatId');
    return res.status(400).send('❌ Provide either chatId or number');
  }

  try {
    await client.sendMessage(targetId, message);
    const info = `✅ Message sent to ${targetId}: "${message}"`;
    console.log(info);
    writeLog(info);
    res.send('✅ Message sent!');
  } catch (err) {
    const errorInfo = `❌ Error sending message to ${targetId}: ${err?.message || String(err)}`;
    console.error(errorInfo);
    writeLog(errorInfo);
    res.status(500).send('❌ Error sending message: ' + (err?.message || String(err)));
  }
});

// upload file (pastikan folder uploads ada)
const upload = multer({ dest: UPLOAD_DIR });

// tebak MIME dari ekstensi (fallback aman)
function guessMimeType(filename) {
  const ext = path.extname(filename).toLowerCase();
  switch (ext) {
    case '.pdf': return 'application/pdf';
    case '.docx': return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    case '.doc': return 'application/msword';
    case '.xlsx': return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    case '.xls': return 'application/vnd.ms-excel';
    case '.zip': return 'application/zip';
    case '.rar': return 'application/vnd.rar';
    case '.jpg':
    case '.jpeg': return 'image/jpeg';
    case '.png': return 'image/png';
    case '.txt': return 'text/plain';
    default: return 'application/octet-stream';
  }
}

// (opsional) batas ukuran file agar tidak block event-loop untuk file sangat besar
function getFileSizeMB(p) {
  try { return fs.statSync(p).size / (1024 * 1024); } catch { return 0; }
}

app.post('/file', upload.single('file'), async (req, res) => {
  if (!isReady) {
    writeLog('❌ Client not ready. File not sent.');
    return res.status(503).send('❌ WhatsApp client not ready yet');
  }

  const { chatId, number } = req.body || {};
  const filePath = req.file?.path;
  const originalName = req.file?.originalname;

  let targetId = '';
  if (chatId) {
    targetId = chatId;
  } else if (number) {
    targetId = number.includes('@g.us') ? number : number + '@c.us';
  } else {
    writeLog('❌ Missing target (chatId/number)');
    if (filePath) try { fs.unlinkSync(filePath); } catch {}
    return res.status(400).send('❌ Provide chatId or number');
  }

  if (!filePath || !originalName) {
    writeLog('❌ Missing file payload');
    return res.status(400).send('❌ Missing file');
  }

  // batas opsional 20MB
  const sizeMB = getFileSizeMB(filePath);
  if (sizeMB > 20) {
    writeLog(`❌ File terlalu besar (${sizeMB.toFixed(2)} MB): ${originalName}`);
    try { fs.unlinkSync(filePath); } catch {}
    return res.status(413).send('❌ File too large');
  }

  try {
    const fileBuffer = fs.readFileSync(filePath);
    const base64Data = fileBuffer.toString('base64');
    const mimeType = guessMimeType(originalName);

    const media = new MessageMedia(mimeType, base64Data, originalName);
    await client.sendMessage(targetId, media);

    writeLog(`📎 File sent to ${targetId}: ${originalName} (${sizeMB.toFixed(2)} MB)`);
    res.send('✅ File sent!');
  } catch (err) {
    writeLog(`❌ Failed to send file to ${targetId}: ` + (err?.message || String(err)));
    res.status(500).send('❌ Failed to send file');
  } finally {
    // hapus temp file
    try { fs.unlinkSync(filePath); } catch (_) {}
  }
});

// jalankan server
const PORT = process.env.PORT || 4000;
app.listen(PORT, () => console.log(`📡 WhatsApp API running on port ${PORT}`));

// --- graceful shutdown: hapus flag saat proses mati -------------------------
function shutdownHandler(signal) {
  return () => {
    writeLog(`🔻 Received ${signal}, cleaning up...`);
    isReady = false;
    clearFlag();
    process.exit(0);
  };
}
process.on('SIGINT', shutdownHandler('SIGINT'));
process.on('SIGTERM', shutdownHandler('SIGTERM'));
// Windows CMD kadang kirim SIGBREAK
process.on('SIGBREAK', shutdownHandler('SIGBREAK'));
process.on('beforeExit', () => { isReady = false; clearFlag(); });
process.on('uncaughtException', (err) => {
  writeLog('💥 Uncaught exception: ' + (err?.stack || err?.message || String(err)));
  isReady = false;
  clearFlag();
  process.exit(1);
});


setInterval(() => {}, 1000);
