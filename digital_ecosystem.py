import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import json

from config import config

logger = logging.getLogger(__name__)

class AssetStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    DELETED = "deleted"

class DigitalAsset:
    def __init__(self, asset_data: Dict[str, Any]):
        self.asset_id = asset_data['asset_id']
        self.user_id = asset_data['user_id']
        self.name = asset_data['name']
        self.tier = asset_data['tier']
        self.value = float(asset_data['value'])
        self.personal_link = asset_data['personal_link']
        self.qr_code_url = asset_data.get('qr_code_url')
        self.created_at = asset_data.get('created_at', datetime.now())
        self.status = AssetStatus(asset_data.get('status', 'active'))
        self.analytics = asset_data.get(
            'analytics',
            {
                'views': 0,
                'clicks': 0,
                'conversions': 0,
                'conversion_rate': 0.0,
                'revenue': 0.0,
                'roi': 0.0,
            },
        )
        self.features = asset_data.get('features', [])
        self.limits = asset_data.get('limits', {})
        self.integrations = asset_data.get('integrations', {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            'asset_id': self.asset_id,
            'user_id': self.user_id,
            'name': self.name,
            'tier': self.tier,
            'value': self.value,
            'personal_link': self.personal_link,
            'qr_code_url': self.qr_code_url,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'status': self.status.value,
            'analytics': self.analytics,
            'features': self.features,
            'limits': self.limits,
            'integrations': self.integrations,
        }

    def calculate_roi(self) -> float:
        if self.value == 0:
            return 0.0
        return (self.analytics['revenue'] / self.value) * 100

    def update_analytics(self, event_type: str, value: float = 1):
        if event_type == 'view':
            self.analytics['views'] += int(value)
        elif event_type == 'click':
            self.analytics['clicks'] += int(value)
        elif event_type == 'conversion':
            self.analytics['conversions'] += int(value)
            self.analytics['revenue'] += value

        if self.analytics['clicks'] > 0:
            self.analytics['conversion_rate'] = (
                self.analytics['conversions'] / self.analytics['clicks'] * 100
            )
        self.analytics['roi'] = self.calculate_roi()

class DigitalEcosystem:
    def __init__(self, database_manager):
        self.db = database_manager
        self.active_assets: Dict[str, DigitalAsset] = {}

    async def create_digital_asset(self, user_id: int, tier: str = 'basic') -> DigitalAsset:
        from user_models import UserManager  # lazy to avoid circular import
        user_manager = UserManager(self.db)
        user = await user_manager.get_user(user_id)
        if not user:
            raise Exception("User not found")

        asset_template = config.ASSET_TIERS.get(tier, config.ASSET_TIERS['basic'])
        asset_data = {
            'asset_id': f"ASSET_{user_id}_{int(datetime.now().timestamp())}",
            'user_id': user_id,
            'name': asset_template['name'],
            'tier': tier,
            'value': asset_template['price'],
            'personal_link': f"https://t.me/{config.BOT_USERNAME}?start=ref_{user_id}",
            'qr_code_url': f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=https://t.me/{config.BOT_USERNAME}?start=ref_{user_id}",
            'features': asset_template['features'],
            'limits': {'max_assets': asset_template['max_assets']},
            'integrations': {
                'telegram_bot': tier != 'basic',
                'web_dashboard': True,
                'mobile_app': tier in ['premium', 'business', 'enterprise'],
                'api_access': tier in ['business', 'enterprise'],
            },
        }
        query = """ 
        INSERT INTO digital_assets 
        (asset_id, user_id, name, tier, value, personal_link, qr_code_url, features, limits, integrations)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """
        result = self.db.execute_query(
            query,
            (
                asset_data['asset_id'],
                asset_data['user_id'],
                asset_data['name'],
                asset_data['tier'],
                asset_data['value'],
                asset_data['personal_link'],
                asset_data['qr_code_url'],
                json.dumps(asset_data['features']),
                json.dumps(asset_data['limits']),
                json.dumps(asset_data['integrations']),
            ),
            commit=True,
        )
        if result:
            asset = DigitalAsset(dict(result[0]))
            self.active_assets[asset.asset_id] = asset
            return asset
        raise Exception("Failed to create digital asset")

    async def get_user_assets(self, user_id: int) -> List[DigitalAsset]:
        query = "SELECT * FROM digital_assets WHERE user_id = %s AND status != 'deleted'"
        results = self.db.execute_query(query, (user_id,))
        assets: List[DigitalAsset] = []
        for row in results:
            asset_data = dict(row)
            for field in ('features', 'limits', 'integrations', 'analytics'):
                if isinstance(asset_data.get(field), str):
                    try:
                        asset_data[field] = json.loads(asset_data[field])
                    except Exception:
                        pass
            assets.append(DigitalAsset(asset_data))
        return assets

    async def calculate_user_portfolio_value(self, user_id: int) -> Dict[str, float]:
        assets = await self.get_user_assets(user_id)
        total_value = sum(a.value for a in assets)
        total_revenue = sum(a.analytics['revenue'] for a in assets)
        total_roi = (total_revenue / total_value * 100) if total_value > 0 else 0.0
        return {
            'total_assets': len(assets),
            'portfolio_value': total_value,
            'total_revenue': total_revenue,
            'average_roi': total_roi,
            'best_performing_asset': max([a.analytics['roi'] for a in assets], default=0),
        }

from database import db
ecosystem = DigitalEcosystem(database_manager=db)
