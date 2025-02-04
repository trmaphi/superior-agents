import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from web3 import Web3
from web3.types import TxParams, Wei
from eth_account import Account
from eth_typing import Address, ChecksumAddress
import json
import requests
from loguru import logger
from typing import Optional, Dict, Any, Union
import asyncio

load_dotenv()


# Settings
class Settings(BaseSettings):
	ETHER_PRIVATE_KEY: str
	ONEINCH_API_KEY: str


settings = Settings(
	ETHER_PRIVATE_KEY=os.getenv("ETHER_PRIVATE_KEY") or "",
	ONEINCH_API_KEY=os.getenv("ONEINCH_API_KEY") or "",
)
app = FastAPI()
web3 = Web3(Web3.HTTPProvider("https://eth.llamarpc.com"))

# Constants
WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
NATIVE_ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
ONEINCH_ROUTER = "0x1111111254EEB25477B68fb85Ed929f73A960582"


class SwapRequest(BaseModel):
	token_in: str = Field(
		...,
		description="Input token address (use 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE for ETH)",
	)
	token_out: str = Field(
		...,
		description="Output token address (use 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE for ETH)",
	)
	amount_in: str = Field(
		..., description="Input amount in smallest denomination (wei for ETH)"
	)
	slippage: float = Field(1.0, description="Slippage tolerance in percentage")


async def check_and_handle_approval(
	token_address: str, amount: str, wallet_address: ChecksumAddress
) -> bool:
	"""Check token allowance and approve if needed."""
	try:
		# Skip approval check for native ETH
		if token_address.lower() == NATIVE_ETH_ADDRESS.lower():
			return True

		# Check current allowance
		allowance_url = f"https://api.1inch.dev/swap/v6.0/1/approve/allowance"
		allowance_response = requests.get(
			allowance_url,
			headers={"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"},
			params={"tokenAddress": token_address, "walletAddress": wallet_address},
		)

		if allowance_response.status_code != 200:
			raise Exception(f"Failed to check allowance: {allowance_response.json()}")

		current_allowance = int(allowance_response.json().get("allowance", "0"))

		# If allowance is sufficient, return True
		if current_allowance >= int(amount):
			return True

		# Get approval transaction
		approve_url = f"https://api.1inch.dev/swap/v6.0/1/approve/transaction"
		approve_response = requests.get(
			approve_url,
			headers={"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"},
			params={"tokenAddress": token_address},
		)

		if approve_response.status_code != 200:
			raise Exception(
				f"Failed to get approval transaction: {approve_response.json()}"
			)

		approve_tx = approve_response.json()

		# Prepare approval transaction
		tx: TxParams = {
			"from": wallet_address,
			"to": Web3.to_checksum_address(approve_tx["to"]),
			"data": approve_tx["data"],
			"nonce": web3.eth.get_transaction_count(wallet_address),
			"gasPrice": web3.eth.gas_price,
			"chainId": 1,  # Ethereum mainnet
			"value": Wei(0),
		}

		# Estimate gas
		gas_limit = web3.eth.estimate_gas(tx)
		tx["gas"] = gas_limit

		# Sign and send approval transaction
		signed_tx = web3.eth.account.sign_transaction(tx, settings.ETHER_PRIVATE_KEY)
		tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)

		# Wait for approval transaction to be mined
		receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
		return receipt["status"] == 1

	except Exception as e:
		logger.error(f"Approval failed: {str(e)}")
		raise Exception(f"Token approval failed: {str(e)}")


@app.post("/api/v1/swap")
async def swap_tokens(request: SwapRequest):
	return JSONResponse({"result": "success!"})


if __name__ == "__main__":
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=9009)
