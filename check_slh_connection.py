
"""
כלי בדיקה מהיר לווידוא חיבור לשרשרת BSC ולטוקן SLH.

שימוש:
    python check_slh_connection.py
"""

from SLH.slh_token import (
    SLH_CHAIN_ID,
    SLH_RPC_URL,
    SLH_TOKEN_ADDRESS,
    SLH_TOKEN_DECIMALS,
    SLH_TOKEN_SYMBOL,
    w3,
)


def main() -> None:
    print("== SLH Network Connectivity Check ==")
    print(f"RPC URL: {SLH_RPC_URL}")
    print(f"Configured Chain ID: {SLH_CHAIN_ID}")
    print(f"Token Address: {SLH_TOKEN_ADDRESS}")
    print(f"Token Decimals: {SLH_TOKEN_DECIMALS}")
    print(f"Token Symbol: {SLH_TOKEN_SYMBOL}")
    print()

    is_connected = w3.is_connected()
    print(f"Web3 connected: {is_connected}")
    if not is_connected:
        print("❌ לא הצלחנו להתחבר לרשת. בדוק את ה-RPC או חיבור האינטרנט מהשרת.")
        return

    try:
        onchain_chain_id = w3.eth.chain_id
        print(f"On-chain Chain ID: {onchain_chain_id}")
        if onchain_chain_id != SLH_CHAIN_ID:
            print("⚠️ אזהרה: ה-Chain ID שהוחזר מהשרשרת שונה מהצפוי!")
    except Exception as e:
        print("⚠️ לא הצלחנו לקרוא את chain_id מהשרשרת:", e)

    print("\nאם הכל ירוק – אפשר לחבר את הבוט וה-API לאותו חוזה SLH ולבנות עליו ארנקים, סטייקינג ועוד.")


if __name__ == "__main__":
    main()
