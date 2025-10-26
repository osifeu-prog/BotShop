import os, json, asyncio, time
from typing import Dict, Any

class JsonStore:
    def __init__(self, path: str = "./data/store.json"):
        self.path = path
        self._lock = asyncio.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path,"w",encoding="utf-8") as f:
                json.dump({"users":{}, "orders":[]}, f)

    async def load(self) -> Dict[str, Any]:
        async with self._lock:
            with open(self.path,"r",encoding="utf-8") as f:
                return json.load(f)

    async def save(self, data: Dict[str, Any]):
        async with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp,"w",encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    async def upsert_user(self, chat_id: int, updates: Dict[str, Any]):
        data = await self.load()
        u = data["users"].setdefault(str(chat_id), {"joined_at": int(time.time())})
        u.update(updates)
        await self.save(data)

    async def get_user(self, chat_id: int):
        data = await self.load()
        return data["users"].get(str(chat_id))
