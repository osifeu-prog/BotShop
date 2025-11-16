from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
REF_FILE = DATA_DIR / "referrals.json"

router = APIRouter()


def _load_referrals() -> Dict[str, Any]:
    if not REF_FILE.exists():
        return {"users": {}}
    try:
        return json.loads(REF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}}


class ReferralUser(BaseModel):
    user_id: int
    referrer: Optional[int] = None


class ReferralStats(BaseModel):
    total_users: int
    total_with_referrer: int
    total_roots: int
    roots: List[int]
    network_sizes: Dict[str, int]


class ReferralNode(BaseModel):
    user_id: int
    referrer: Optional[int]
    children: List[int]
    path_to_root: List[int]


@router.get("/api/referral/stats", response_model=ReferralStats)
async def referral_stats():
    data = _load_referrals()
    users = data.get("users", {})

    total_users = len(users)
    total_with_referrer = sum(1 for u in users.values() if u.get("referrer"))
    roots: List[int] = []
    for uid, u in users.items():
        if not u.get("referrer"):
            try:
                roots.append(int(uid))
            except ValueError:
                continue

    # בונים גרף ילדים לכל משתמש
    children_map: Dict[str, List[str]] = {}
    for uid, u in users.items():
        children_map.setdefault(uid, [])
    for uid, u in users.items():
        ref = u.get("referrer")
        if ref:
            children_map.setdefault(str(ref), []).append(uid)

    def bfs_size(root_id: str) -> int:
        seen: Set[str] = set()
        queue: List[str] = [root_id]
        while queue:
            cur = queue.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            for ch in children_map.get(cur, []):
                if ch not in seen:
                    queue.append(ch)
        return len(seen)

    network_sizes: Dict[str, int] = {}
    for r in roots:
        s = bfs_size(str(r))
        network_sizes[str(r)] = s

    return ReferralStats(
        total_users=total_users,
        total_with_referrer=total_with_referrer,
        total_roots=len(roots),
        roots=roots,
        network_sizes=network_sizes,
    )


@router.get("/api/referral/tree/{user_id}", response_model=ReferralNode)
async def referral_tree(user_id: int):
    data = _load_referrals()
    users = data.get("users", {})

    suid = str(user_id)
    if suid not in users:
        raise HTTPException(status_code=404, detail="user not found in referral map")

    # מי הפנה אותו
    ref_raw = users[suid].get("referrer")
    referrer: Optional[int] = int(ref_raw) if ref_raw else None

    # מי הילדים שלו
    children: List[int] = []
    for uid, u in users.items():
        if u.get("referrer") == suid:
            try:
                children.append(int(uid))
            except ValueError:
                continue

    # מסלול עד השורש
    path_to_root: List[int] = []
    cur = suid
    seen: Set[str] = set()
    while True:
        if cur in seen:
            break
        seen.add(cur)
        path_to_root.append(int(cur))
        ref = users.get(cur, {}).get("referrer")
        if not ref:
            break
        cur = str(ref)

    return ReferralNode(
        user_id=user_id,
        referrer=referrer,
        children=children,
        path_to_root=path_to_root,
    )
