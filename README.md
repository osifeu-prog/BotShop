# NIFTII – בוט חנות (Telegram) + תגמולי SLH על BSC

בוט טלגרם עם UI שיווקי, גלריית דמו, נתיב רכישה, והפצת תגמולים On-Chain במטבע **"סלה ללא גבולות" (SLH)** על גבי Binance Smart Chain.

## מה יש כאן
- `main.py` – שרת AIOHTTP + וובהוק טלגרם, UI מלא, העברת אישורי תשלום לקבוצת תשלומים, תגמול on-chain.
- `images/` – תמונות למסכי פתיחה/גלריה. שים כאן קבצי JPG/PNG.
- `requirements.txt`, `Dockerfile`, `.gitignore`, `runtime.txt`.

## הפעלה מקומית
```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
