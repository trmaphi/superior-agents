from abc import ABC, abstractmethod
from typing import Callable, List, Tuple

from ollama import ChatResponse, chat
from result import Err, Ok, Result

from src.config import (
	OllamaConfig,
)
from src.types import ChatHistory


class Genner(ABC):
	def __init__(self, identifier: str, do_stream: bool):
		self.identifier = identifier
		self.do_stream = do_stream

	@abstractmethod
	def ch_completion(self, messages: ChatHistory) -> Result[str, str]:
		"""Generate a single strategy based on the current chat history.

		Args:
			messages (ChatHistory): Chat history

		Return:
			Ok(str): The raw response
			Err(str): The error message
		"""
		pass

	def set_do_stream(self, final_state: bool):
		self.do_stream = final_state

	@abstractmethod
	def generate_code(
		self, messages: ChatHistory, blocks: List[str] = [""]
	) -> Result[Tuple[List[str], str], str]:
		"""Generate a single strategy based on the current chat history.

		Args:
			messages (ChatHistory): Chat history
			blocks: (List(str)): Will extract inside of the XML tag first before processing it into code

		Returns:
			Ok:
				str: Processed code
				str: Raw response
			Err:
				List[str]: List of error messages
		"""
		pass

	@abstractmethod
	def generate_list(
		self, messages: ChatHistory, blocks: List[str] = [""]
	) -> Result[Tuple[List[List[str]], str], str]:
		"""Generate a list of strategies based on the current chat history.

		Args:
			messages (ChatHistory): Chat history
			blocks: (List(str)): Will extract inside of the XML tag first before processing it into list

		Returns:
			Ok:
				List[str]: Processed list
				str: Raw response
			Err:
				List[str]: List of error messages
		"""
		pass

	@abstractmethod
	def extract_code(
		self, response: str, blocks: List[str] = []
	) -> Result[List[str], str]:
		"""Extract the code from the response.

		Args:
			response (str): The raw response
			blocks: (List(str)): Will extract inside of the XML tag first before processing it into code

		Returns:
			Ok:
				List[str]: Processed code
			Err:
				List[str]: List of error messages
		"""
		pass

	@abstractmethod
	def extract_list(
		self, response: str, block_name: List[str] = []
	) -> Result[List[List[str]], str]:
		"""Extract a list of strategies from the response.

		Args:
			response (str): The raw response
			blocks: (List(str)): Will extract inside of the XML tag first before processing it into list

		Returns:
			Ok:
				List[str]: List of strategies
			Err:
				str: List of error messages
		"""
		pass


class OllamaGenner(Genner):
	def __init__(
		self,
		config: OllamaConfig,
		identifier: str,
		stream_fn: Callable[[str], None] | None,
	):
		super().__init__(identifier, True if stream_fn else False)

		self.config = config
		self.stream_fn = stream_fn

	def ch_completion(self, messages: ChatHistory) -> Result[str, str]:
		final_response = ""
		try:
			assert self.config.model is not None, "Model name is not provided"

			if self.do_stream:
				assert self.stream_fn is not None

				for chunk in chat(self.config.model, messages.as_native(), stream=True):
					if chunk["message"] and chunk["message"]["content"]:
						token = chunk["message"]["content"]
						self.stream_fn(token)
						final_response += token
			else:
				response: ChatResponse = chat(self.config.model, messages.as_native())
				assert (
					response.message.content is not None
				), "No content in the response"

				final_response = response.message.content
		except AssertionError as e:
			return Err(
				f"OllamaGenner.ch_completion: response.message.content is None: {e}"
			)
		except Exception as e:
			return Err(
				f"An unexpected Ollama error while generating code with {self.config.name}, raw response: {response} occured: \n{e}"
			)

		return Ok(final_response)

	def generate_code(
		self, messages: ChatHistory, blocks: List[str] = [""]
	) -> Result[Tuple[List[str], str], str]:
		try:
			completion_result = self.ch_completion(messages)

			if err := completion_result.err():
				return Err(
					f"OllamaGenner.generate_code: completion_result.is_err(): \n{err}"
				)

			raw_response = completion_result.unwrap()

			extract_code_result = self.extract_code(raw_response, blocks)

			if err := extract_code_result.err():
				return Err(
					f"OllamaGenner.generate_code: extract_code_result.is_err(): \n{err}"
				)

			processed_code = extract_code_result.unwrap()

			return Ok((processed_code, raw_response))
		except Exception as e:
			return Err(
				f"An unexpected error while generating code with {self.config.name}, raw response: {raw_response} occured: \n{e}"
			)

	def generate_list(
		self, messages: ChatHistory, blocks: List[str] = [""]
	) -> Result[Tuple[List[List[str]], str], str]:
		try:
			completion_result = self.ch_completion(messages)

			if err := completion_result.err():
				return Err(
					f"OllamaGenner.generate_list: completion_result.is_err(): \n{err}"
				)

			raw_response = completion_result.unwrap()

			extract_list_result = self.extract_list(raw_response, blocks)

			if err := extract_list_result.err():
				return Err(
					f"OllamaGenner.generate_list: extract_list_result.is_err(): \n{err}"
				)

			extracted_list = extract_list_result.unwrap()

			return Ok((extracted_list, raw_response))

		except Exception as e:
			return Err(
				f"An unexpected error while generating list with {self.config.name}, raw response: {raw_response} occured: \n{e}"
			)
