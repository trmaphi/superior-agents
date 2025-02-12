import json
from os import write
import sqlite3
from datetime import datetime
from textwrap import dedent


def dict_factory(cursor, row):
	"""Convert database rows to dictionaries"""
	fields = [column[0] for column in cursor.description]
	return {key: value for key, value in zip(fields, row)}


def get_connection(db_path: str = "db/agentic_yaitsiu.db") -> sqlite3.Connection:
	"""Create a database connection with dictionary row factory"""
	conn = sqlite3.connect(db_path)
	conn.row_factory = dict_factory
	return conn


def format_datetime(dt_str: str | None) -> str:
	"""Format datetime string to human readable format"""
	if not dt_str:
		return "Not yet"
	try:
		dt = datetime.fromisoformat(dt_str)
		return dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception as e:
		return dt_str


def print_strategies(conn: sqlite3.Connection):
	"""Print all strategies in a readable format"""
	cursor = conn.cursor()
	cursor.execute("""
		SELECT * FROM strategy_data 
		ORDER BY id DESC
	""")
	strategies = cursor.fetchall()

	print("\n=== STRATEGIES ===")
	print(f"Total strategies: {len(strategies)}")
	print("=" * 80)

	for strategy in strategies:
		print(f"\nStrategy #{strategy['id']}")
		print(f"Name: {strategy['name']}")
		print(f"Inserted at: {format_datetime(strategy['inserted_at'])}")
		print(f"Ran at: {format_datetime(strategy['ran_at'])}")
		print(f"Result: {strategy['strategy_result'] or 'Not executed'}")
		if strategy["reasoning"]:
			print(f"Reasoning: {strategy['reasoning']}")
		print("-" * 40)


def print_chat_history(conn: sqlite3.Connection):
	"""Print all chat messages in a readable format"""
	cursor = conn.cursor()
	cursor.execute("""
		SELECT * FROM chat_history 
		ORDER BY id
	""")
	messages = cursor.fetchall()

	print("\n=== CHAT HISTORY ===")
	print(f"Total messages: {len(messages)}")
	print("=" * 80)

	for msg in messages:
		print(f"\nMessage #{msg['id']}")
		print(f"Role: {msg['role']}")
		print(f"Content: {msg['content']}")
		if msg["metadata"]:
			print(f"Metadata: {msg['metadata']}")
		print("-" * 40)

def write_chat_history(conn: sqlite3.Connection):
	cursor = conn.cursor()
	cursor.execute("""
		SELECT * FROM chat_history 
		ORDER BY id
	""")

	messages = cursor.fetchall()

	for msg in messages:
		with open("./db/test.txt", "a") as f:
			str_ = ""
			str_ += f"\nMessage #{msg['id']}\n"
			str_ += f"Role: {msg['role']}\n"
			str_ += f"Content: {msg['content']}\n"
			if msg["metadata"]:
				str_ += f"Metadata: {msg['metadata']}\n"

			f.write(dedent(str_))

def write_chat_history_json(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM chat_history 
        ORDER BY id
    """)
    messages = cursor.fetchall()
    
    # Convert messages to a list of dictionaries
    chat_history = []
    for msg in messages:
        message_dict = {
            "id": msg["id"],
            "role": msg["role"],
            "content": msg["content"]
        }
        if msg["metadata"]:
            message_dict["metadata"] = msg["metadata"]
        
        chat_history.append(message_dict)
    
    # Write to JSON file
    with open("./db/chat_history.json", "w") as f:
        json.dump({"messages": chat_history}, f, indent=2, ensure_ascii=False)		

def main():
	try:
		conn = get_connection()
		print_strategies(conn)
		print_chat_history(conn)
		write_chat_history(conn)
		write_chat_history_json(conn)
		conn.close()
	except Exception as e:
		print(f"Error accessing database: {e}")


if __name__ == "__main__":
	main()
