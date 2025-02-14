from eth_typing import Address
from web3 import Web3
import requests
from typing import Dict, Any
from datetime import datetime

from typing import Optional
import requests
from dataclasses import dataclass


@dataclass
class SuperAgentResponse:
	address: str
	error: Optional[str] = None


def get_superagent_account(
	network: str,
	agent_id: str,
	api_key: str,
	base_url: str,
) -> SuperAgentResponse:
	"""
	Get SuperAgent account address for a given network and agent name.

	Args:
	    network: Network identifier (e.g., "eth")
	    agent_name: Name of the agent (e.g., "phi")
	    api_key: API key for authentication
	    base_url: Base URL for the API

	Returns:
	    SuperAgentResponse containing the address or error message
	"""
	headers = {"Content-Type": "application/json", "x-api-key": api_key}

	payload = {
		"jsonrpc": "2.0",
		"method": "superAgent_getAccount",
		"params": [network, agent_id],
		"id": 0,
	}

	try:
		response = requests.post(base_url, headers=headers, json=payload, timeout=30)
		response.raise_for_status()

		result = response.json()
		if "error" in result:
			return SuperAgentResponse(address="", error=str(result["error"]))

		return SuperAgentResponse(address=result["result"])

	except requests.exceptions.RequestException as e:
		return SuperAgentResponse(address="", error=f"Request failed: {str(e)}")
	except Exception as e:
		return SuperAgentResponse(address="", error=f"Unexpected error: {str(e)}")


def get_wallet_stats(
	agent_id: str,
	infura_project_id: str,
	etherscan_key: str,
	vault_base_url: str ,
	vault_api_key: str,
) -> Dict[str, Any]:
	"""
	Get basic wallet stats and token holdings
	Returns a dict with ETH balance and token information
	"""
	w3 = Web3(Web3.HTTPProvider(f"https://mainnet.infura.io/v3/{infura_project_id}"))

	response = get_superagent_account(
		network="eth", agent_id=agent_id, api_key=vault_api_key, base_url=vault_base_url
	)

	if response.error:
		raise Exception("Failed to get the eth address of agent_id")

	# Convert wallet address to checksum
	address = w3.to_checksum_address(response.address)

	# Get ETH balance
	eth_balance = w3.eth.get_balance(address)  # type: ignore
	eth_balance_human = w3.from_wei(eth_balance, "ether")

	# Get tokens from Etherscan
	url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&sort=desc&apikey={etherscan_key}"
	response = requests.get(url)
	data = response.json()

	tokens = {}
	if data.get("status") == "1" and "result" in data:
		token_txns = data["result"]
		if isinstance(token_txns, list):
			for tx in token_txns:
				if isinstance(tx, dict):
					# Convert token address to checksum format
					try:
						token_addr = w3.to_checksum_address(
							tx.get("contractAddress", "")
						)
						if token_addr and token_addr not in tokens:
							# Simple contract to get balance
							contract = w3.eth.contract(
								address=token_addr,
								abi=[
									{
										"constant": True,
										"inputs": [
											{"name": "_owner", "type": "address"}
										],
										"name": "balanceOf",
										"outputs": [
											{"name": "balance", "type": "uint256"}
										],
										"type": "function",
									}
								],
							)

							balance = contract.functions.balanceOf(address).call()
							decimal = int(tx.get("tokenDecimal", "18"))
							if balance > 0:
								tokens[token_addr] = {
									"symbol": tx.get("tokenSymbol", "UNKNOWN"),
									"balance": balance / (10**decimal),
								}
					except Exception as e:
						print(
							f"Error processing token {tx.get('contractAddress')}: {str(e)}"
						)
						continue

	return {
		"eth_balance": float(eth_balance_human),
		"tokens": tokens,
		"timestamp": datetime.now().isoformat(),
	}
