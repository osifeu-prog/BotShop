import csv, json, os, time, threading, uuid
from typing import Dict, Any, List

class JsonStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        base = os.path.dirname(self.path)
        if base and not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"users": {}})

    def _read(self) -> Dict[str, Any]:
        with self._lock:
            if not os.path.exists(self.path):
                return {"users": {}}
            with open(self.path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception:
                    return {"users": {}}

    def _write(self, data: Dict[str, Any]):
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    # ---- Users ----
    def ensure_user(self, chat_id: int) -> Dict[str, Any]:
        data = self._read()
        u = data["users"].get(str(chat_id))
        if not u:
            u = {"joined_at": int(time.time()), "paid": False, "wallet": "", "notes": "", "history": []}
            data["users"][str(chat_id)] = u
            self._write(data)
        return u

    def update_user(self, chat_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        data = self._read()
        u = data["users"].get(str(chat_id), {"joined_at": int(time.time()), "history": []})
        u.update(updates)
        data["users"][str(chat_id)] = u
        self._write(data)
        return u

    def append_history(self, chat_id: int, entry: Dict[str, Any]) -> Dict[str, Any]:
        data = self._read()
        u = data["users"].get(str(chat_id))
        if not u:
            u = {"joined_at": int(time.time()), "paid": False, "wallet": "", "notes": "", "history": []}
        u.setdefault("history", [])
        u["history"].insert(0, entry)  # newest first
        data["users"][str(chat_id)] = u
        self._write(data)
        return u

    def get_user(self, chat_id: int) -> Dict[str, Any]:
        data = self._read()
        return data["users"].get(str(chat_id), {})

    def all_users(self) -> Dict[str, Any]:
        data = self._read()
        return data.get("users", {})

# ---- Receipts CSV ----
class ReceiptBook:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        base = os.path.dirname(self.csv_path)
        if base and not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["deal_id","ts","chat_id","method","amount_nis","amount_usd","status"])

    def add(self, deal_id: str, ts: int, chat_id: int, method: str, amount_nis: float, amount_usd: float, status: str):
        with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([deal_id, ts, chat_id, method, f"{amount_nis:.2f}", f"{amount_usd:.2f}", status])

def new_deal_id() -> str:
    return uuid.uuid4().hex[:10]