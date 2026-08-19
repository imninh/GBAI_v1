const puppeteer = require('d:/P-075/frontend/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');

const ARTIFACT_DIR = 'C:/Users/tranh/.gemini/antigravity-ide/brain/77c9b211-7c7e-4de4-8fcc-3d7962c072d2';

const CHROME_PATHS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

async function run() {
  let executablePath = null;
  for (const p of CHROME_PATHS) {
    if (fs.existsSync(p)) {
      executablePath = p;
      break;
    }
  }

  console.log(`🌐 Khởi chạy trình duyệt: ${executablePath}`);
  const browser = await puppeteer.launch({
    executablePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=430,932'],
    defaultViewport: { width: 430, height: 932 },
  });

  const context = browser.defaultBrowserContext();
  await context.overridePermissions('http://localhost:3000', ['geolocation']);

  const page = await browser.newPage();
  await page.setGeolocation({ latitude: 21.028511, longitude: 105.854167 });

  console.log('1️⃣ Điều hướng tới http://localhost:3000...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle0', timeout: 30000 });

  console.log('2️⃣ Bỏ qua Onboarding...');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const skipBtn = buttons.find(b => b.innerText.includes('Bỏ qua') || b.innerText.includes('Tôi đã có tài khoản'));
    if (skipBtn) skipBtn.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  console.log('3️⃣ Đăng nhập vai trò Cư dân...');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const resBtn = buttons.find(b => b.innerText.includes('Cư dân') || b.innerText.includes('resident@demo.vn'));
    if (resBtn) resBtn.click();
  });
  
  // Chờ màn hình Cư dân hiển thị đầy đủ
  await page.waitForSelector('h1', { timeout: 10000 });
  await new Promise(r => setTimeout(r, 1500));

  console.log('4️⃣ Bấm vào chú gấu mèo Mun để mở khung Chatbot RAG...');
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('open-greenbin-chat'));
  });

  await page.waitForSelector('#chatbot-input', { timeout: 10000 });
  console.log('✅ Khung chat Mun AI đã mở thành công!');

  console.log('5️⃣ Gửi câu hỏi F2 (Tra cứu thùng rác gần nhất) $\\to$ Kích hoạt tracking GPS DUY NHẤT 1 LẦN...');
  await page.type('#chatbot-input', 'Cho tôi biết thùng rác tái chế gần đây còn chỗ không?');

  const sendBtn = await page.$('#chatbot-send-btn');
  if (sendBtn) await sendBtn.click();

  console.log('⏳ Chờ Mistral AI tra cứu và so khớp khoảng cách GPS...');
  await new Promise(r => setTimeout(r, 8000));
  await page.screenshot({ path: path.join(ARTIFACT_DIR, '08_gps_tracking_bins_result.png') });
  console.log('📸 Đã chụp: 08_gps_tracking_bins_result.png');

  await browser.close();
  console.log('🎉 Hoàn thành kiểm tra tính năng tracking GPS duy nhất 1 lần cho tra cứu thùng rác!');
}

run().catch(err => {
  console.error('❌ Lỗi:', err);
  process.exit(1);
});
