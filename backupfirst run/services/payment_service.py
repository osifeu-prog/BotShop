from ..config import Config

class PaymentService:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def link_for(self, chat_id: int) -> str:
        base = self.cfg.payment_link_base.rstrip("/")
        return f"{base}?uid={chat_id}&amt={int(self.cfg.entry_price_nis)}"