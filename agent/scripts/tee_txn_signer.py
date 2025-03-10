import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from web3 import Web3, Account
from retry import retry
from typing import Optional

load_dotenv()


# Settings
class Settings(BaseSettings):
	ETHER_PRIVATE_KEY: str
	ONEINCH_API_KEY: str


settings = Settings(
	ETHER_PRIVATE_KEY=os.getenv("ETHER_PRIVATE_KEY") or "",
	ONEINCH_API_KEY=os.getenv("ONEINCH_API_KEY") or "",
)


class RateLimitException(Exception):
	def __init__(self, message="Rate limit exceeded"):
		self.message = message
		super().__init__(self.message)


app = FastAPI()
web3 = Web3(
	Web3.HTTPProvider(
		f"https://eth-mainnet.g.alchemy.com/v2/cR5K5OtFcvSLttJ5OQIcRNyd0ZBJpwnF"
	)
)


# API Models
class SwapRequest(BaseModel):
	token_in: str = Field(..., description="Input token address")
	token_out: str = Field(..., description="Output token address")
	amount_in: str = Field(..., description="Input amount in smallest denomination")
	slippage: float = Field(0.5, description="Slippage tolerance in percentage")
	# deadline_minutes: int = Field(20, description="Transaction deadline in minutes")


class SwapResponse(BaseModel):
	transaction_hash: Optional[str]
	status: str
	error: Optional[str] = None


class QuoteRequest(BaseModel):
	token_in: str
	token_out: str
	amount_in: str


class QuoteResponse(BaseModel):
	amount_out: str
	# price_impact: float
	# minimum_received: str


# API Endpoints
@app.get("/health")
async def health_check():
	return {
		"status": "healthy",
		# "eth_address": ETHER_ADDRESS[:6] + "..." + ETHER_ADDRESS[-4:] if ETHER_ADDRESS else "Not set"
	}


nonce = None


def use_nonce(address):
	global nonce
	if nonce is None:
		nonce = web3.eth.get_transaction_count(address)
		return nonce
	nonce += 1
	return nonce


# Construct full API request URL
def apiRequestUrl(methodName, queryParams):
	return f"https://api.1inch.dev/swap/v6.0/1/{methodName}?{'&'.join([f'{key}={value}' for key, value in queryParams.items()])}"


@retry(RateLimitException, delay=1)
def check_allowance(tokenAddress, walletAddress):
	url = apiRequestUrl(
		"/approve/allowance",
		{"tokenAddress": tokenAddress, "walletAddress": walletAddress},
	)
	response = requests.get(
		url, headers={"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
	)
	if response.status_code == 429:
		raise RateLimitException()
	data = response.json()
	return data.get("allowance")


@retry(RateLimitException, delay=1)
def build_approval_tx(
	token_address, amount, address=None
):  # Assuming you have defined apiRequestUrl() function to construct the URL
	url = apiRequestUrl(
		"/approve/transaction",
		{
			"tokenAddress": token_address,
			"amount": 115792089237316195423570985008687907853269984665640564039457584007913129639935,
		}
		if amount
		else {"tokenAddress": token_address},
	)
	response = requests.get(
		url, headers={"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"}
	)
	if response.status_code == 429:
		raise RateLimitException()
	transaction = response.json()
	return transaction


@retry(RateLimitException, delay=1)
def build_swap_tx(request: SwapRequest, address):
	apiUrl = "https://api.1inch.dev/swap/v6.0/1/swap"
	requestOptions = {
		"headers": {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"},
		"params": {
			"src": request.token_in,
			"dst": request.token_out,
			"amount": request.amount_in,
			"from": address,
			"eoa": address,
			"slippage": request.slippage,
			"disableEstimate": True,
		},
	}

	# Prepare request components
	headers = requestOptions.get("headers", {})
	params = requestOptions.get("params", {})

	response = requests.get(apiUrl, headers=headers, params=params)
	print("response:", response.text)
	if response.status_code == 429:
		raise RateLimitException()

	if response.status_code != 200:
		raise HTTPException(status_code=response.status_code, detail=response.text)

	response_json = response.json()
	return response_json.get("tx")


def estimate_gas_price():
	base_fee = web3.eth.gas_price
	priority_fee = 2000000000  # 2 Gwei in wei
	total_fee = base_fee + priority_fee

	return total_fee  # this is returned in wei


@retry(RateLimitException, delay=1)
def build_and_send_transaction(transaction, address):
	# Convert all addresses to checksum format
	transaction["to"] = Web3.to_checksum_address(transaction["to"])
	transaction["from"] = Web3.to_checksum_address(address)
	# If there's data field, decode it to find and convert any addresses
	if "data" in transaction:
		# Keep the original data
		transaction["data"] = transaction["data"]

	# Remove any fields that shouldn't be in the transaction
	send_transaction = {
		"from": transaction["from"],
		"to": transaction["to"],
		"data": transaction["data"],
	}

	# use the function to retrieve how many gwei to use for gas
	total_fee = estimate_gas_price()

	# convert Wei to Gwei
	fee_gwei = web3.from_wei(total_fee, "gwei")
	print("Reasonable fee: " + str(fee_gwei) + " Gwei")

	send_transaction["nonce"] = use_nonce(address)
	send_transaction["gasPrice"] = total_fee
	print("transaction:", send_transaction)

	gas_limit = (
		transaction["gas"]
		if "gas" in transaction
		else web3.eth.estimate_gas(send_transaction, "latest")
	)

	print("-" * 30)
	# calculate and display how much ETH is used as gas
	gas_fee = estimate_gas_price() * gas_limit
	print("Ether paid as gas fee: " + str(web3.from_wei(gas_fee, "ether")) + " ETH")

	send_transaction["gas"] = gas_limit

	signed_transaction = web3.eth.account.sign_transaction(
		send_transaction, settings.ETHER_PRIVATE_KEY
	)
	tx_hash = web3.eth.send_raw_transaction(signed_transaction.raw_transaction)

	return {"transaction_hash": web3.to_hex(tx_hash), "status": "success"}


@app.post("/api/v1/swap")
async def swap_tokens(
	request: SwapRequest,
	# swapper: UniswapSwapper = Depends(get_swapper)
):
	address = Web3.to_checksum_address(
		Account.from_key(settings.ETHER_PRIVATE_KEY).address
	)
	allowance = check_allowance(request.token_in, address)
	print("allowance:", allowance)
	if int(allowance) < int(request.amount_in):
		approval_tx = build_approval_tx(request.token_in, request.amount_in, address)
		build_and_send_transaction({**approval_tx, "gas": 50_000}, address)

	swap_tx = build_swap_tx(request, address)
	result = build_and_send_transaction(swap_tx, address)
	return result


def oneInchQuote(request: QuoteRequest):
	apiUrl = "https://api.1inch.dev/swap/v6.0/1/quote"
	requestOptions = {
		"headers": {"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"},
		"params": {
			"src": request.token_in,
			"dst": request.token_out,
			"amount": request.amount_in,
			"includeProtocols": True,
			"includeGas": True,
		},
	}

	# Prepare request components
	headers = requestOptions.get("headers", {})
	params = requestOptions.get("params", {})

	response = requests.get(apiUrl, headers=headers, params=params)
	if response.status_code != 200:
		print(response.json())
		return JSONResponse(status_code=response.status_code, content=response.json())

	response_json = response.json()
	return QuoteResponse(amount_out=response_json["dstAmount"])


# def okxQuote(request: QuoteRequest):
#     # OKX API credentials
#     secret_key = settings.OKX_SECRET_KEY

#     # Get ISO timestamp
#     timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

#     # Construct the request path with query parameters
#     method = "GET"
#     request_path = f"/api/v5/dex/aggregator/quote?amount={request.amount_in}&chainId=1&toTokenAddress={request.token_out}&fromTokenAddress={request.token_in}"

#     # Create signature
#     message = timestamp + method + request_path
#     signature = base64.b64encode(
#         hmac.new(
#             secret_key.encode('utf-8'),
#             message.encode('utf-8'),
#             hashlib.sha256
#         ).digest()
#     ).decode('utf-8')

#     # Construct headers
#     headers = {
#         'Content-Type': 'application/json',
#         'OK-ACCESS-KEY': settings.OKX_API_KEY ,
#         'OK-ACCESS-SIGN': signature,
#         'OK-ACCESS-TIMESTAMP': timestamp,
#         'OK-ACCESS-PASSPHRASE': settings.OKX_PASSPHRASE
#     }

#     # Make the request
#     response = requests.get(
#         f"https://www.okx.com{request_path}",
#         headers=headers
#     )

#     if response.status_code != 200:
#         print(response.json())
#         return JSONResponse(status_code=response.status_code, content=response.json())

#     response_json = response.json()
#     print(json.dumps(response_json, indent=4))  # Debug print

#     # Check if response is successful and has data
#     if response_json.get("code") == "0" and response_json.get("data"):
#         data = response_json["data"][0]  # Get first item from data array
#         return QuoteResponse(
#             amount_out=data["toTokenAmount"]
#         )
#     else:
#         return JSONResponse(
#             status_code=400,
#             content={"error": "Invalid response from OKX", "details": response_json}
#         )


@app.post("/api/v1/quote")
async def get_quote(
	request: QuoteRequest,
	# swapper: UniswapSwapper = Depends(get_swapper)
):
	oneInchQuoteResponse = oneInchQuote(request)
	# okxQuoteResponse = okxQuote(request)
	return oneInchQuoteResponse


if __name__ == "__main__":
	import uvicorn

	uvicorn.run(app, host="0.0.0.0", port=9009)
