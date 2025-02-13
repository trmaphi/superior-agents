import base64
from datetime import datetime, timezone
import hashlib
import hmac
import os
import json
import requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from web3 import Web3
from eth_account import Account
from functools import lru_cache
from retry import retry
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    class Config:
        env_file = ".env"
        extra = "ignore"

    ETHER_PRIVATE_KEY: str
    ONEINCH_API_KEY: str

    # OKX_API_KEY: str
    # OKX_SECRET_KEY: str
    # OKX_PASSPHRASE: str


class RateLimitException(Exception):
    def __init__(self, message="Rate limit exceeded"):
        self.message = message
        super().__init__(self.message)


settings = Settings()

# Initialize FastAPI app
app = FastAPI(title="Uniswap Swap API")

web3 = Web3(Web3.HTTPProvider(f'https://eth-mainnet.g.alchemy.com/v2/cR5K5OtFcvSLttJ5OQIcRNyd0ZBJpwnF'))

class UniswapSwapper:
    def __init__(self):
        # Initialize Web3 with Infura
        self.private_key = settings.ETHER_PRIVATE_KEY
        self.address = Web3.to_checksum_address(self.w3.eth.account.from_key(self.private_key).address)
        
        # Uniswap V2 Router address (Ethereum Mainnet)
        self.router_address = Web3.to_checksum_address('0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D')
        
        # Router ABI
        self.router_abi = json.loads(open("./docker/uniswap_router_abi.json").read())
        
        # ERC20 ABI
        self.erc20_abi = json.loads(open("./docker/erc_20_abi.json").read())
        
        self.router_contract = self.w3.eth.contract(
            address=self.router_address,
            abi=self.router_abi
        )
        self.nonce = self.w3.eth.get_transaction_count(self.address)

    def useNonce(self):
        self.nonce += 1
        return self.nonce

    def get_token_contract(self, token_address: str):
        """Create a token contract instance."""
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=self.erc20_abi
        )

    def approve_token(self, token_address: str, amount: int) -> bool:
        """Approve the router to spend tokens."""
        try:
            token_contract = self.get_token_contract(token_address)
            
            approve_txn = token_contract.functions.approve(
                self.router_address,
                amount
            ).build_transaction({
                'from': self.address,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.useNonce(),
            })
            
            signed_txn = self.w3.eth.account.sign_transaction(approve_txn, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            return receipt.status == 1
            
        except Exception as e:
            print(f"Error in approve_token: {str(e)}")
            return False

    def swap_tokens(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: Optional[int] = None,
        slippage: float = 0.5,
        deadline_minutes: int = 20
    ) -> Optional[str]:
        """Perform a token swap on Uniswap V2."""
        try:
            token_in = Web3.to_checksum_address(token_in)
            token_out = Web3.to_checksum_address(token_out)
            
            if not self.approve_token(token_in, amount_in):
                raise Exception("Token approval failed")
            
            if min_amount_out is None:
                amounts_out = self.router_contract.functions.getAmountsOut(
                    amount_in,
                    [token_in, token_out]
                ).call()
                min_amount_out = int(amounts_out[1] * (1 - slippage/100))
            
            deadline = self.w3.eth.get_block('latest').timestamp + (deadline_minutes * 60)
            
            swap_txn = self.router_contract.functions.swapExactTokensForTokens(
                amount_in,
                min_amount_out,
                [token_in, token_out],
                self.address,
                deadline
            ).build_transaction({
                'from': self.address,
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.address),
            })
            
            gas_estimate = self.w3.eth.estimate_gas(swap_txn)
            swap_txn['gas'] = int(gas_estimate * 1.2)
            
            signed_txn = self.w3.eth.account.sign_transaction(swap_txn, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                return self.w3.to_hex(tx_hash)
            else:
                raise Exception("Transaction failed")
            
        except Exception as e:
            print(f"Error in swap_tokens: {str(e)}")
            return None

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

# Create singleton instance
@lru_cache()
def get_swapper():
    return UniswapSwapper()

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
    url = apiRequestUrl("/approve/allowance", {"tokenAddress": tokenAddress, "walletAddress": walletAddress})
    response = requests.get(url, headers={"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"})
    if response.status_code == 429:
        raise RateLimitException()
    data = response.json()
    return data.get("allowance")

@retry(RateLimitException, delay=1)
def build_approval_tx(token_address, amount, address=None):    # Assuming you have defined apiRequestUrl() function to construct the URL
    url = apiRequestUrl("/approve/transaction", {"tokenAddress": token_address, "amount": 115792089237316195423570985008687907853269984665640564039457584007913129639935} if amount else {"tokenAddress": token_address})
    response = requests.get(url, headers={"Authorization": f"Bearer {settings.ONEINCH_API_KEY}"})
    if response.status_code == 429:
        raise RateLimitException()
    transaction = response.json()
    return transaction

@retry(RateLimitException, delay=1)
def build_swap_tx(request: SwapRequest, address):
    apiUrl = "https://api.1inch.dev/swap/v6.0/1/swap"
    requestOptions = {
        "headers": {
            "Authorization": f"Bearer {settings.ONEINCH_API_KEY}"
        },
        "params": {
            "src": request.token_in,
            "dst": request.token_out,
            "amount": request.amount_in,
            "from": address,
            "eoa": address,
            "slippage": request.slippage,
        }
    }

    # Prepare request components
    headers = requestOptions.get("headers", {})
    params = requestOptions.get("params", {})


    response = requests.get(apiUrl, headers=headers, params=params)
    print("response:", response.text)
    if response.status_code == 429:
        raise RateLimitException()  
    
    response_json = response.json()
    return response_json.get("tx")

def estimate_gas_price():
    base_fee = web3.eth.gas_price
    priority_fee = 2000000000 # 2 Gwei in wei
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
    fee_gwei = web3.from_wei(total_fee, 'gwei')
    print('Reasonable fee: ' + str(fee_gwei) + ' Gwei')

    send_transaction["nonce"] = use_nonce(address)
    send_transaction["gasPrice"] = total_fee
    print("transaction:", send_transaction)

    gas_limit = transaction["gas"] if "gas" in transaction else web3.eth.estimate_gas(send_transaction, "latest")

    print('-' * 30)
    # calculate and display how much ETH is used as gas 
    gas_fee = estimate_gas_price() * gas_limit
    print('Ether paid as gas fee: ' + str(web3.from_wei(gas_fee, 'ether')) + ' ETH')

    send_transaction["gas"] = gas_limit

    signed_transaction = web3.eth.account.sign_transaction(send_transaction, settings.ETHER_PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_transaction.raw_transaction)

    return {
        "transaction_hash": web3.to_hex(tx_hash),
        "status": "success"
    }

@app.post("/api/v1/swap")
async def swap_tokens(
    request: SwapRequest,
    # swapper: UniswapSwapper = Depends(get_swapper)
):
    address = Web3.to_checksum_address(Account.from_key(settings.ETHER_PRIVATE_KEY).address)
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
        "headers": {
                "Authorization": f"Bearer {settings.ONEINCH_API_KEY}"
        },
        "params": {
            "src": request.token_in,
            "dst": request.token_out,
            "amount": request.amount_in,
            "includeProtocols": True,
            "includeGas": True,
        }
    }

    # Prepare request components
    headers = requestOptions.get("headers", {})
    params = requestOptions.get("params", {})


    response = requests.get(apiUrl, headers=headers, params=params)
    if response.status_code != 200:
        print(response.json())
        return JSONResponse(status_code=response.status_code, content=response.json())
    
    response_json = response.json()
    return QuoteResponse(
        amount_out=response_json["dstAmount"]
    )

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
    
@app.get("/api/v1/balance/{token_address}")
async def get_balance(
    token_address: str,
    swapper: UniswapSwapper = Depends(get_swapper)
):
    try:
        if not Web3.is_address(token_address):
            raise HTTPException(status_code=400, detail="Invalid token address")

        token_contract = swapper.get_token_contract(token_address)
        balance = token_contract.functions.balanceOf(swapper.address).call()

        return {
            "address": swapper.address,
            "token_address": token_address,
            "balance": str(balance)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run with: uvicorn filename:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9009)