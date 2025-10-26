import asyncio, os, ujson as json, time
from typing import Dict, Any

class JsonStore:
    def __init__(self, path: str, cache_ttl: int=2):
        self.path = path
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Any] | None = None
        self._loaded = 0.0
        self._ttl = cache_ttl
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    async def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path,"r",encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"users":{}, "balances":{}, "orders":[]}

    async def _save(self, data: Dict[str, Any]):
        tmp = self.path + ".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(tmp,self.path)

    async def get(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache is None or (now - self._loaded) > self._ttl:
            async with self._lock:
                self._cache = await self._load()
                self._loaded = now
        return self._cache

    async def update(self, mutator):
        async with self._lock:
            data = await self._load()
            mutator(data)
            await self._save(data)
            self._cache = data
            self._loaded = time.time()