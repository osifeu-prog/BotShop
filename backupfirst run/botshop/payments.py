PAYMENT_BANK_NAME   = "בנק הפועלים"
PAYMENT_BANK_BRANCH = "153 — כפר גנים"
PAYMENT_BANK_ACCOUNT= "73462"
PAYMENT_BANK_OWNER  = "קאופמן צביקה"

PAYPAL_URL   = "https://paypal.me/osifdu"
PHONE_PAY    = "0546671882"  # ביט / פייבוקס
TON_WALLET   = "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp"

def payment_text() -> str:
    return (
        "💳 *אפשרויות תשלום להצטרפות:*\n\n"
        "🏦 *העברה בנקאית*\n"
        f"{PAYMENT_BANK_NAME}\nסניף: {PAYMENT_BANK_BRANCH}\n"
        f"ח-ן: `{PAYMENT_BANK_ACCOUNT}`\nמוטב: {PAYMENT_BANK_OWNER}\n\n"
        f"📱 *ביט/PayBox*: `{PHONE_PAY}`\n"
        f"🌐 *PayPal*: {PAYPAL_URL}\n\n"
        f"🪙 *ארנק TON*: `{TON_WALLET}`\n\n"
        "לאחר תשלום  שלח/י כאן צילום אסמכתה ונאשר ידנית ✅"
    )