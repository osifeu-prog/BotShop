from typing import Dict, Any, List
from ..storage.json_store import JsonStore
from ..models.user import User, Balance
from ..models.order import Order, OrderType

class UserService:
    def __init__(self, store: JsonStore):
        self.store = store

    async def ensure_user(self, chat_id: int):
        async def m(d):
            uid = str(chat_id)
            d["users"].setdefault(uid, {"paid":False,"wallet":"","joined_at":0})
            d["balances"].setdefault(uid, {"slh":0.0,"bnb":0.0})
        await self.store.update(m)

    async def get_user(self, chat_id: int) -> User:
        d = await self.store.get(); u = d["users"].get(str(chat_id))
        if not u: return User(chat_id=chat_id)
        return User(chat_id=chat_id, paid=bool(u.get("paid")), wallet=u.get("wallet",""), joined_at=int(u.get("joined_at",0)))

    async def set_paid(self, chat_id: int, paid: bool):
        async def m(d):
            uid = str(chat_id)
            d["users"].setdefault(uid, {"paid":False,"wallet":"","joined_at":0})
            d["users"][uid]["paid"]=paid
        await self.store.update(m)

    async def set_wallet(self, chat_id: int, addr: str):
        async def m(d):
            uid=str(chat_id)
            d["users"].setdefault(uid, {"paid":False,"wallet":"","joined_at":0})
            d["users"][uid]["wallet"]=addr
        await self.store.update(m)

    async def add_balance(self, chat_id:int, slh:float=0.0, bnb:float=0.0):
        async def m(d):
            uid=str(chat_id)
            b = d["balances"].setdefault(uid, {"slh":0.0,"bnb":0.0})
            b["slh"] = round(b.get("slh",0.0)+slh, 8)
            b["bnb"] = round(b.get("bnb",0.0)+bnb, 8)
        await self.store.update(m)

    async def get_balance(self, chat_id:int) -> Balance:
        d=await self.store.get(); b=d["balances"].get(str(chat_id), {"slh":0.0,"bnb":0.0})
        return Balance(slh=float(b.get("slh",0.0)), bnb=float(b.get("bnb",0.0)))

    async def add_order(self, o: Order):
        async def m(d):
            d["orders"].append({
                "id": o.id, "type": o.type.value, "from": o.frm, "to": o.to,
                "amount": o.amount, "asset": o.asset, "status": o.status, "ts": o.ts
            })
        await self.store.update(m)

    async def list_orders_for(self, chat_id: int) -> List[Dict[str,Any]]:
        d = await self.store.get()
        return [o for o in d["orders"] if o.get("from")==chat_id or o.get("to")==chat_id]