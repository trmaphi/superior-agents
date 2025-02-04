#!/usr/bin/env python3
import sys
import time
import random
import subprocess
import argparse
from typing import Union, List
import re
import os


class SlowTerminal:
	def __init__(
		self,
		line_duration: float = 0.005,
		line_pause: float = 0.1,
		thinking_probability: float = 0.01,
	):
		"""
		Initialize SlowTerminal with customizable parameters

		Args:
		    line_duration: Seconds it should take to type each line
		    line_pause: Seconds to pause between lines
		    thinking_probability: Probability of inserting a longer thinking pause
		"""
		self.line_duration = line_duration
		self.line_pause = line_pause
		self.thinking_probability = thinking_probability
		# ANSI escape sequence pattern
		self.ansi_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

	def get_visible_length(self, text: str) -> int:
		"""Get the visible length of text excluding ANSI escape sequences"""
		return len(self.ansi_pattern.sub("", text))

	def split_with_ansi(self, text: str) -> List[str]:
		"""Split text into chunks preserving ANSI escape sequences"""
		chunks = []
		last_end = 0

		# Find all ANSI escape sequences
		for match in self.ansi_pattern.finditer(text):
			# Add text before the escape sequence
			if match.start() > last_end:
				chunks.extend(list(text[last_end : match.start()]))
			# Add the escape sequence as a single chunk
			chunks.append(text[match.start() : match.end()])
			last_end = match.end()

		# Add remaining text
		if last_end < len(text):
			chunks.extend(list(text[last_end:]))

		return chunks

	def type_text(self, text: str) -> None:
		"""Type each line at a consistent speed while preserving colors"""
		# Strip trailing newline as we'll handle it separately
		text = text.rstrip("\n")

		if not text:  # Skip empty lines
			return

		# Calculate delay based on visible text length
		visible_length = self.get_visible_length(text)
		if visible_length == 0:
			visible_length = 1  # Avoid division by zero
		char_delay = self.line_duration / visible_length

		# Split text into chunks (characters and ANSI sequences)
		chunks = self.split_with_ansi(text)

		# Type each chunk
		for chunk in chunks:
			sys.stdout.write(chunk)
			sys.stdout.flush()
			# Only delay for visible characters
			if not self.ansi_pattern.match(chunk):
				time.sleep(char_delay)

		# Add newline and pause
		sys.stdout.write("\n")
		sys.stdout.flush()

		if random.random() < self.thinking_probability:
			time.sleep(random.uniform(1.0, 2.0))
		else:
			time.sleep(self.line_pause)

	def run_command(self, command: Union[str, List[str]]) -> None:
		"""Run a command and show its output with timed typing"""
		if isinstance(command, str):
			command = command.split()

		try:
			process = subprocess.Popen(
				command,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				universal_newlines=True,
				env={"FORCE_COLOR": "1", **dict(os.environ)},  # Force color output
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
		description="Simulate slow terminal output with color support"
	)
	parser.add_argument("command", nargs="+", help="Command to execute")
	parser.add_argument(
		"--line-duration",
		type=float,
		default=0.5,
		help="Seconds to spend typing each line",
	)
	parser.add_argument(
		"--line-pause", type=float, default=0.8, help="Seconds to pause between lines"
	)
	parser.add_argument(
		"--think-prob",
		type=float,
		default=0.05,
		help="Probability of longer thinking pause",
	)

	args = parser.parse_args()

	terminal = SlowTerminal(
		line_duration=args.line_duration,
		line_pause=args.line_pause,
		thinking_probability=args.think_prob,
	)

	terminal.run_command(args.command)


if __name__ == "__main__":
	main()
