import os

from dotenv import load_dotenv
import requests
from loguru import logger


def get_secrets_from_vault():
	"""Fetch secrets from HashiCorp Vault and set them as environment variables"""
	try:
		# Load credentials from .env first
		load_dotenv()

		client_id = os.getenv("VAULT_CLIENT_ID")
		client_secret = os.getenv("VAULT_CLIENT_SECRET")
		org_id = os.getenv("VAULT_ORGANIZATION_ID")
		project_id = os.getenv("VAULT_PROJECT_ID")
		app_name = os.getenv("VAULT_APP_NAME")

		if not all([client_id, client_secret, org_id, project_id, app_name]):
			logger.info(
				"Vault credentials not found in .env, falling back to local environment variables"
			)
			return

		# Get the access token
		auth_url = "https://auth.hashicorp.com/oauth/token"
		auth_data = {
			"grant_type": "client_credentials",
			"client_id": client_id,
			"client_secret": client_secret,
			"audience": "https://api.hashicorp.cloud",
		}

		auth_response = requests.post(auth_url, data=auth_data)
		if auth_response.status_code != 200:
			print(f"Failed to get auth token. Status: {auth_response.status_code}")
			return

		access_token = auth_response.json()["access_token"]

		# Get all secrets at once using the :open endpoint
		base_url = "https://api.cloud.hashicorp.com/secrets/2023-11-28"
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json",
		}

		# Pagination logic
		next_page_token = None
		while True:
			secrets_url = f"{base_url}/organizations/{org_id}/projects/{project_id}/apps/{app_name}/secrets:open"

			# Add pagination token if available

			if next_page_token:
				secrets_url += f"?pagination.next_page_token={next_page_token}"
			logger.info(secrets_url)

			response = requests.get(secrets_url, headers=headers)

			if response.status_code == 200:
				secrets_data = response.json()

				# Load secrets into environment variables
				for secret in secrets_data.get("secrets", []):
					name = secret["name"]
					value = secret["static_version"]["value"]
					os.environ[name] = value
					logger.info(f"Loaded secret: {name} from Vault")

				# Check for next page token
				next_page_token = secrets_data.get("pagination", {}).get(
					"next_page_token"
				)
				logger.info(next_page_token)
				if not next_page_token:
					break  # No more pages, exit the loop
			else:
				logger.error(
					f"Failed to get secrets from Vault. Status: {response.status_code}"
				)
				logger.info("Falling back to local environment variables")

				break

	except Exception as e:
		logger.error(f"Error fetching secrets from Vault: {str(e)}")
		logger.error("Falling back to local environment variables")
