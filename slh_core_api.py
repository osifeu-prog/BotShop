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
VISITS_FILE = DATA_DIR / "referral_visits.json"

router = APIRouter()


def _safe_read(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_referrals() -> Dict[str, Any]:
    return _safe_read(REF_FILE, {"users": {}})


def _save_referrals(data: Dict[str, Any]) -> None:
    REF_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_visits() -> Dict[str, Any]:
    return _safe_read(VISITS_FILE, {"visits": []})


def _save_visits(data: Dict[str, Any]) -> None:
    VISITS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


class ReferralVisitIn(BaseModel):
    referrer_id: Optional[int] = None
    landing_variant: Optional[str] = None
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None


class ReferralVisitOut(BaseModel):
    total_visits: int
    by_referrer: Dict[str, int]


class ReferralGraph(BaseModel):
    nodes: List[Dict[str, Any]]
    links: List[Dict[str, Any]]


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
    for uid in users.keys():
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


@router.post("/api/referral/track_visit", response_model=ReferralVisitOut)
async def track_visit(payload: ReferralVisitIn):
    visits = _load_visits()
    vlist: List[Dict[str, Any]] = visits.setdefault("visits", [])
    rec = {
        "referrer_id": payload.referrer_id,
        "landing_variant": payload.landing_variant,
        "utm_source": payload.utm_source,
        "utm_campaign": payload.utm_campaign,
    }
    vlist.append(rec)
    _save_visits(visits)

    # סטטוס מקוצר
    counts: Dict[str, int] = {}
    for v in vlist:
        key = str(v.get("referrer_id") or "none")
        counts[key] = counts.get(key, 0) + 1

    return ReferralVisitOut(
        total_visits=len(vlist),
        by_referrer=counts,
    )


@router.get("/api/referral/graph", response_model=ReferralGraph)
async def referral_graph():
    data = _load_referrals()
    users = data.get("users", {})

    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []

    for uid, u in users.items():
        ref = u.get("referrer")
        nodes.append(
            {
                "id": int(uid),
                "referrer": int(ref) if ref else None,
            }
        )
        if ref:
            try:
                links.append(
                    {
                        "source": int(ref),
                        "target": int(uid),
                    }
                )
            except ValueError:
                continue

    return ReferralGraph(nodes=nodes, links=links)
