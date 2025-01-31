from contextlib import contextmanager
import signal
import re


@contextmanager
def timeout(seconds: int):
	def timeout_handler(signum, frame):
		raise TimeoutError(f"Execution timed out after {seconds} seconds")

	# Set the timeout handler
	original_handler = signal.signal(signal.SIGALRM, timeout_handler)
	signal.alarm(seconds)

	try:
		yield
	finally:
		# Restore the original handler and cancel the alarm
		signal.alarm(0)
		signal.signal(signal.SIGALRM, original_handler)


def extract_content(text: str, block_name: str) -> str:
	"""
	Extract content between custom XML-like tags.

	Args:
		text (str): The input text containing XML-like blocks
		block_name (str): The name of the block to extract content from

	Returns:
		str: The content between the specified tags, or None if not found

	Example:
		>>> text = "<ASdasdas>\ncontent1\n</ASdasdas>\n<asdasdasdas>\ncontent2\n</asdasdasdas>"
		>>> extract_content(text, "ASdasdas")
		'content1'
	"""
	if block_name == "":
		return text

	pattern = rf"<{block_name}>\s*(.*?)\s*</{block_name}>"

	# Search for the pattern in the text
	match = re.search(pattern, text, re.DOTALL)

	# Return the content if found, None otherwise
	return match.group(1).strip() if match else ""
