import pandas as pd

hashes = pd.read_csv("input.csv")["hash"].tolist()

formatted_hashes  = [f'"{hash}",' for hash in hashes]
hash_list_str = "\n".join(formatted_hashes)

with open("formatted_hashes.csv", "w") as f:
    f.write("hash\n")  # Header
    for hash_val in hash_list_str.splitlines():
        f.write(f"{hash_val}\n")

