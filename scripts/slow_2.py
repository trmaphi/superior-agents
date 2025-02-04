import sys
import time
import random
import argparse
import subprocess
import re
import os
from typing import List, Union


class SlowTerminal:
	def __init__(
		self,
		line_duration: float = 0.0005,  # Reduced default duration
		line_pause: float = 0,
		thinking_probability: float = 0.01,
		chunk_size: int = 3,  # New parameter for batch processing
	):
		self.line_duration = line_duration
		self.line_pause = line_pause
		self.thinking_probability = thinking_probability
		self.chunk_size = chunk_size
		self.ansi_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

	def get_visible_length(self, text: str) -> int:
		return len(self.ansi_pattern.sub("", text))

	def split_with_ansi(self, text: str) -> List[str]:
		chunks = []
		last_end = 0
		current_chunk = []

		for match in self.ansi_pattern.finditer(text):
			if match.start() > last_end:
				text_chunk = text[last_end : match.start()]
				current_chunk.extend(text_chunk)

				while len(current_chunk) >= self.chunk_size:
					chunks.append("".join(current_chunk[: self.chunk_size]))
					current_chunk = current_chunk[self.chunk_size :]

			chunks.append(text[match.start() : match.end()])
			last_end = match.end()

		if last_end < len(text):
			remaining_text = text[last_end:]
			current_chunk.extend(remaining_text)

		while current_chunk:
			chunk_size = min(self.chunk_size, len(current_chunk))
			chunks.append("".join(current_chunk[:chunk_size]))
			current_chunk = current_chunk[chunk_size:]

		return chunks

	def type_text(self, text: str) -> None:
		text = text.rstrip("\n")
		if not text:
			return

		visible_length = self.get_visible_length(text)
		if visible_length == 0:
			visible_length = 1

		char_delay = self.line_duration / visible_length
		chunks = self.split_with_ansi(text)

		for chunk in chunks:
			sys.stdout.write(chunk)
			sys.stdout.flush()
			if not self.ansi_pattern.match(chunk):
				time.sleep(char_delay)

		sys.stdout.write("\n")
		sys.stdout.flush()

		if random.random() < self.thinking_probability:
			time.sleep(random.uniform(0.5, 1.0))  # Reduced thinking time
		else:
			time.sleep(self.line_pause)

	def run_command(self, command: Union[str, List[str]]) -> None:
		if isinstance(command, str):
			command = command.split()

		try:
			process = subprocess.Popen(
				command,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				universal_newlines=True,
				env={"FORCE_COLOR": "1", **os.environ},
			)

			while True:
				output = process.stdout.readline()
				if output == "" and process.poll() is not None:
					break
				if output:
					self.type_text(output)

		except subprocess.CalledProcessError as e:
			print(f"Error executing command: {e}")
			sys.exit(1)


def main():
	parser = argparse.ArgumentParser(
		description="Simulate smooth terminal output with color support"
	)
	parser.add_argument("command", nargs="+", help="Command to execute")
	parser.add_argument(
		"--line-duration",
		type=float,
		default=0.2,
		help="Seconds to spend typing each line",
	)
	parser.add_argument(
		"--line-pause", type=float, default=0.1, help="Seconds to pause between lines"
	)
	parser.add_argument(
		"--think-prob",
		type=float,
		default=0.05,
		help="Probability of longer thinking pause",
	)
	parser.add_argument(
		"--chunk-size", type=int, default=3, help="Characters to output at once"
	)

	args = parser.parse_args()
	terminal = SlowTerminal(
		line_duration=args.line_duration,
		line_pause=args.line_pause,
		thinking_probability=args.think_prob,
		chunk_size=args.chunk_size,
	)
	terminal.run_command(args.command)


if __name__ == "__main__":
	main()
