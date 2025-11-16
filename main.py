# ... (previous code remains the same)

# =========================
# FastAPI + lifespan
# =========================

app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    בזמן עליית השרת:
    1. מגדירים webhook ב-Telegram ל-WEBHOOK_URL
    2. מפעילים את אפליקציית ה-Telegram
    3. אם יש DB – מרימים schema
    """
    logger.info("Setting Telegram webhook to %s", WEBHOOK_URL)
    await ptb_app.bot.setWebhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)

    # init DB schema אם זמין
    if DB_AVAILABLE:
        try:
            init_schema()
            logger.info("DB schema initialized.")
        except Exception as e:
            logger.error("Failed to init DB schema: %s", e)

    async with ptb_app:
        logger.info("Starting Telegram Application")
        await ptb_app.start()
        yield
        logger.info("Stopping Telegram Application")
        await ptb_app.stop()

app = FastAPI(lifespan=lifespan)

# =========================
# API Routes for Website
# =========================

@app.get("/")
async def serve_site():
    """מגיש את אתר האינטרנט"""
    return FileResponse("docs/index.html")

@app.get("/site")
async def serve_site_alt():
    """מגיש את אתר האינטרנט (alias)"""
    return FileResponse("docs/index.html")

@app.get("/api/posts")
async def get_posts(limit: int = 20):
    """API לפוסטים חברתיים"""
    if not DB_AVAILABLE:
        return {"items": []}
    
    try:
        from db import get_social_posts
        posts = get_social_posts(limit)
        return {"items": posts}
    except Exception as e:
        logger.error("Failed to get posts: %s", e)
        return {"items": []}

@app.get("/api/token/sales")
async def get_token_sales(limit: int = 50):
    """API למכירות טוקנים"""
    if not DB_AVAILABLE:
        return {"items": []}
    
    try:
        from db import get_token_sales
        sales = get_token_sales(limit)
        return {"items": sales}
    except Exception as e:
        logger.error("Failed to get token sales: %s", e)
        return {"items": []}

@app.get("/api/token/price")
async def get_token_price():
    """API לשער הטוקן"""
    return {
        "official_price_nis": 444,
        "currency": "ILS",
        "updated_at": datetime.utcnow().isoformat()
    }

@app.get("/config/public")
async def get_public_config():
    """API להגדרות ציבוריות"""
    return {
        "slh_nis": 39,
        "business_group_link": os.environ.get("COMMUNITY_GROUP_LINK", "https://t.me/+HIzvM8sEgh1kNWY0"),
        "paybox_url": os.environ.get("PAYBOX_URL"),
        "bit_url": os.environ.get("BIT_URL"),
        "paypal_url": os.environ.get("PAYPAL_URL")
    }

@app.get("/admin/dashboard")
async def admin_dashboard(token: str = ""):
    """דשבורד ניהול HTML"""
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    html_content = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <title>Admin Dashboard - Buy My Shop</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; margin: 20px; }
            .card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        </style>
    </head>
    <body>
        <h1>Admin Dashboard - Buy My Shop</h1>
        <div id="stats"></div>
        <script>
            fetch('/admin/stats?token=' + new URLSearchParams(window.location.search).get('token'))
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stats').innerHTML = `
                        <div class="stats">
                            <div class="card">משתמשים: ${data.payments_stats?.total || 0}</div>
                            <div class="card">אושרו: ${data.payments_stats?.approved || 0}</div>
                            <div class="card">ממתינים: ${data.payments_stats?.pending || 0}</div>
                        </div>
                    `;
                });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

@app.post("/api/telegram-login")
async def handle_telegram_login(user_data: dict):
    """מטפל בהתחברות מטלגרם"""
    try:
        print(f"🔐 Telegram login: {user_data}")
        
        # כאן תוכל לשמור את המשתמש ב-DB
        if DB_AVAILABLE:
            try:
                from db import store_user
                store_user(
                    user_id=user_data['id'],
                    username=user_data.get('username'),
                    first_name=user_data.get('first_name'),
                    last_name=user_data.get('last_name')
                )
            except Exception as e:
                logger.error(f"Failed to store Telegram user: {e}")
        
        return {
            "status": "success", 
            "message": "Login successful",
            "user_id": user_data['id']
        }
        
    except Exception as e:
        logger.error(f"Telegram login error: {e}")
        return {"status": "error", "message": str(e)}

# =========================
# Routes – Webhook + Health + Admin Stats API
# =========================

@app.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """נקודת ה-webhook שטלגרם קורא אליה"""
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)

    if is_duplicate_update(update):
        logger.warning("Duplicate update_id=%s – ignoring", update.update_id)
        return Response(status_code=HTTPStatus.OK.value)

    await ptb_app.process_update(update)
    return Response(status_code=HTTPStatus.OK.value)

@app.get("/health")
async def health():
    """Healthcheck ל-Railway / ניטור"""
    return {
        "status": "ok",
        "service": "telegram-gateway-community-bot",
        "db": "enabled" if DB_AVAILABLE else "disabled",
    }

@app.get("/admin/stats")
async def admin_stats(token: str = ""):
    """
    דשבורד API קטן לקריאה בלבד.
    להשתמש ב-ADMIN_DASH_TOKEN ב-ENV.
    """
    if not ADMIN_DASH_TOKEN or token != ADMIN_DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not DB_AVAILABLE:
        return {"db": "disabled"}

    try:
        stats = get_approval_stats()
        monthly = get_monthly_payments(datetime.utcnow().year, datetime.utcnow().month)
        top_ref = get_top_referrers(5)
    except Exception as e:
        logger.error("Failed to get admin stats: %s", e)
        raise HTTPException(status_code=500, detail="DB error")

    return {
        "db": "enabled",
        "payments_stats": stats,
        "monthly_breakdown": monthly,
        "top_referrers": top_ref,
    }

# ... (rest of the code remains the same)
