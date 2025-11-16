# Buy My Shop  Gateway Minimal

שער כניסה מינימלי לקהילת העסקים שלך, מותאם ל-Railway ולתצורת המשתנים הקיימת.

## מה הבוט עושה?

1. כל `/start`:
   - שולח הודעת לוג לקבוצת האדמינים (ADMIN_LOG_CHAT_ID) עם:
     - Chat ID
     - User ID
     - Username
     - Full name
   - שולח למשתמש טקסט הסבר + כפתורים:
     - איך מצטרפים?
     - שליחת הוכחת תשלום
     - תמיכה טכנית
     - קישור לאתר LANDING_URL

2. הצטרפות ותשלום:
   - מסך "איך מצטרפים" מציג:
     - סכום ההצטרפות (SLH_NIS, ברירת מחדל 39)
     - קישורי תשלום אם הוגדרו: PAYBOX_URL, PAYPAL_URL, BIT_URL
   - המשתמש לוחץ "שליחת הוכחת תשלום" ושולח תמונה/מסמך.
   - הבוט מעביר את האישור לקבוצת האדמינים (ADMIN_LOG_CHAT_ID) עם כל הפרטים.

3. תמיכה טכנית:
   - המשתמש לוחץ "תמיכה טכנית", כותב הודעה.
   - הבוט מעביר את ההודעה לקבוצת התמיכה (SUPPORT_GROUP_ID).

4. אישור תשלום:
   - בקבוצת האדמינים שולחים: `/approve <user_id>`
   - הבוט שולח למשתמש שנרשם:
     - הודעה שהתשלום אושר
     - קישור לקבוצת העסקים BUSINESS_GROUP_URL / GROUP_STATIC_INVITE

## מבנה הפרויקט

- `main.py`  אפליקציית FastAPI + אינטגרציית Telegram Webhook
- `requirements.txt`  תלויות מינימליות
- `Procfile`  הפעלת uvicorn ב-Railway
- `docs/index.html`  דף תדמיתי פשוט (נגיש ב-`/site/index.html`)

## משתני סביבה נדרשים (Railway)

הבוט משתמש רק בחלק מהמשתנים שיש לך כבר ב-Railway.
אין צורך למחוק משתנים מיותרים  הם פשוט יתעלמו.

### חובה

- `BOT_TOKEN`  טוקן של הבוט בטלגרם
- `WEBHOOK_URL`  לדוגמה: `https://webwook-production-4861.up.railway.app/webhook`
- `BOT_USERNAME`  לדוגמה: `Buy_My_Shop_bot`

- `ADMIN_LOG_CHAT_ID`  מספר `chat_id` של קבוצת הלוגים/אדמינים  
  (הקבוצה שלך: https://t.me/+aww1rlTDUSplODc0)

- `SUPPORT_GROUP_ID`  מספר `chat_id` של קבוצת התמיכה  
  (https://t.me/+1ANn25HeVBoxNmRk)

- `BUSINESS_GROUP_URL`  לינק ההצטרפות לקהילת העסקים  
  (לדוגמה: https://t.me/+HIzvM8sEgh1kNWY0)

### מומלץ

- `LANDING_URL`  כתובת האתר הראשי (לדוגמה: `https://slh-nft.com`)
- `PAYBOX_URL`  לינק PayBox לתשלום 39 
- `PAYPAL_URL`  לינק PayPal שלך
- `BIT_URL`  טלפון להעברת Bit / העברה בנקאית (לפי מה שהצגת עד עכשיו)
- `SLH_NIS`  סכום ההצטרפות (ברירת מחדל 39)

### משתנים קיימים ברלווי שהקוד המינימלי לא משתמש בהם

לא חובה למחוק, אבל אפשר אם רוצים סדר:

- `ADMIN_DASH_TOKEN`
- `AI_DAILY_QUOTA_FREE`
- `AI_DAILY_QUOTA_PAID`
- `AI_ENABLE`
- `AI_POINTS_THRESHOLD`
- `HF_IMAGE_MODEL`
- `HF_TEXT_MODEL`
- `HF_TOKEN`
- `OPENAI_API_KEY`
- `START_IMAGE_PATH`
- וכל שאר משתני AI / Dashboard / Layer מתקדמת.

הם לא ישפיעו על גרסה זו.

## איך לפרוס

1. ודא שהקבצים למעלה קיימים בריפו שמחובר ל-Railway.
2. `git add . && git commit -m "minimal gateway bot" && git push`.
3. ב-Railway:
   - Root Directory = שורש הריפו (שם `main.py` ו-`Procfile`).
   - השתמש בפקודת הweb מה-Procfile (Railpack עושה זאת לבד).
4. עדכן את משתני הסביבה הדרושים.
5. עשה Deploy מחדש.

בדיקות:

- פתח `/health`  אמור להחזיר JSON עם `status: "ok"`.
- פתח `/site/index.html`  אמור להציג את דף התדמית.
- שלח `/start` לבוט:
  - אתה אמור לראות הודעת לוג בקבוצת האדמינים.
  - המשתמש מקבל טקסט + כפתורי הצטרפות/תשלום/תמיכה.
- שלח צילום אישור תשלום  אמור להגיע לקבוצת האדמינים.
- בקבוצת האדמינים נסה `/approve <user_id>`  המשתמש אמור לקבל קישור לקבוצת העסקים.

מכאן אפשר לחדש פרסום ממומן ולמדוד:
- כמות פתיחות `/start` מהלידים.
- כמות הוכחות תשלום שמגיעות.
- כמה אישורים / הצטרפויות בפועל.

