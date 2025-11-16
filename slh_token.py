import os
import logging
from typing import Optional, Dict, Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger("slhnet.token")


def get_web3() -> Web3:
    rpc_url = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        logger.warning("Web3 is not connected to %s", rpc_url)
    # רשתות בסגנון BSC לפעמים דורשות middleware של POA
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def erc20_contract(w3: Web3, token_address: str):
    abi = [
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        },
    ]
    return w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)


def get_token_metadata() -> Dict[str, Any]:
    token_address = os.getenv("SLH_TOKEN_ADDRESS", "0xACb0A09414CEA1C879c67bB7A877E4e19480f022")
    w3 = get_web3()
    contract = erc20_contract(w3, token_address)
    try:
        name = contract.functions.name().call()
        symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
    except Exception as e:
        logger.exception("Failed to fetch token metadata: %s", e)
        name = "SLH Token"
        symbol = "SLH"
        decimals = 18

    return {
        "address": token_address,
        "name": name,
        "symbol": symbol,
        "decimals": decimals,
    }

