from pathlib import Path

# Gets the absolute path of the directory where THIS script lives
BASE_DIR = Path(__file__).resolve().parent

print(BASE_DIR)