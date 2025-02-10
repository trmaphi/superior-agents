from src.sensor.trading import TradingSensor
import os
from dotenv import load_dotenv

load_dotenv()

sensor = TradingSensor(
	eth_address=str(os.getenv("ETHER_ADDRESS")),
	infura_project_id=str(os.getenv("INFURA_PROJECT_ID")),
	etherscan_api_key=str(os.getenv("ETHERSCAN_KEY")),
)

print(sensor.get_portfolio_status())
