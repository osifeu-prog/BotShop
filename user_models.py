from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class UserTier(Enum):
    BASIC = "basic"
    PREMIUM = "premium"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"

class UserStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"

class DigitalUser:
    """Advanced user representation"""

    def __init__(self, user_data: Dict[str, Any]):
        self.user_id = user_data['user_id']
        self.username = user_data.get('username')
        self.first_name = user_data.get('first_name')
        self.last_name = user_data.get('last_name')
        self.phone = user_data.get('phone')
        self.email = user_data.get('email')
        self.tier = UserTier(user_data.get('tier', 'basic'))
        self.status = UserStatus(user_data.get('status', 'active'))
        self.registration_date = user_data.get('registration_date', datetime.now())
        self.last_active = user_data.get('last_active', datetime.now())
        self.total_earnings = float(user_data.get('total_earnings', 0))
        self.settings = user_data.get('settings', {})

        self.financial_data = {
            'total_revenue': float(user_data.get('total_revenue', 0)),
            'pending_payouts': float(user_data.get('pending_payouts', 0)),
            'lifetime_value': float(user_data.get('lifetime_value', 0)),
            'avg_monthly_earnings': float(user_data.get('avg_monthly_earnings', 0)),
        }

        self.network_stats = {
            'direct_referrals': user_data.get('direct_referrals', 0),
            'total_network': user_data.get('total_network', 0),
            'network_depth': user_data.get('network_depth', 0),
            'conversion_rate': float(user_data.get('conversion_rate', 0)),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'phone': self.phone,
            'email': self.email,
            'tier': self.tier.value,
            'status': self.status.value,
            'registration_date': self.registration_date.isoformat() if isinstance(self.registration_date, datetime) else self.registration_date,
            'last_active': self.last_active.isoformat() if isinstance(self.last_active, datetime) else self.last_active,
            'total_earnings': self.total_earnings,
            'financial_data': self.financial_data,
            'network_stats': self.network_stats,
            'settings': self.settings,
        }

    def calculate_network_value(self) -> float:
        base_value = self.network_stats['total_network'] * 10
        tier_multiplier = {
            UserTier.BASIC: 1.0,
            UserTier.PREMIUM: 1.5,
            UserTier.BUSINESS: 2.0,
            UserTier.ENTERPRISE: 3.0,
        }
        return base_value * tier_multiplier.get(self.tier, 1.0)

    def get_performance_score(self) -> float:
        conversion_score = min(self.network_stats['conversion_rate'] * 10, 50)
        revenue_score = min(self.financial_data['total_revenue'] / 100, 30)
        network_score = min(self.network_stats['total_network'] / 2, 20)
        return conversion_score + revenue_score + network_score

class UserManager:
    """High-level DB access for users"""

    def __init__(self, database_manager):
        self.db = database_manager

    async def create_user(self, user_data: Dict[str, Any]) -> DigitalUser:
        query = """
        INSERT INTO users (user_id, username, first_name, last_name, phone, email, tier)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """
        result = self.db.execute_query(
            query,
            (
                user_data['user_id'],
                user_data.get('username'),
                user_data.get('first_name'),
                user_data.get('last_name'),
                user_data.get('phone'),
                user_data.get('email'),
                user_data.get('tier', 'basic'),
            ),
            commit=True,
        )
        if result:
            return DigitalUser(dict(result[0]))
        raise Exception("Failed to create user")

    async def get_user(self, user_id: int) -> Optional[DigitalUser]:
        query = "SELECT * FROM users WHERE user_id = %s"
        result = self.db.execute_query(query, (user_id,))
        if result:
            return DigitalUser(dict(result[0]))
        return None
