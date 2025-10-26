import json, os, time, asyncio, typing as t

class JsonStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()

    def _ensure(self):
        d = os.path.dirname(self.path)
        if d and not os.path.exists(d): os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path,"w",encoding="utf-8") as f:
                json.dump({"users":{}, "deals":[]}, f, ensure_ascii=False)

    async def load(self) -> dict:
        self._ensure()
        async with self._lock:
            with open(self.path,"r",encoding="utf-8") as f:
                return json.load(f)

    async def save(self, data: dict):
        self._ensure()
        async with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    async def upsert_user(self, chat_id: int, updates: dict):
        data = await self.load()
        u = data["users"].setdefault(str(chat_id), {"joined_at": int(time.time()), "paid": False})
        u.update(updates)
        await self.save(data)

    async def get_user(self, chat_id: int) -> dict | None:
        data = await self.load()
        return data["users"].get(str(chat_id))