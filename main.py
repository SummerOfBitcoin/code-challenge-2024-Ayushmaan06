import os
import json
import hashlib
import binascii
import ecdsa
import multiprocessing
import numpy

# Set the difficulty target
TARGET_DIFFICULTY = "0000ffff00000000000000000000000000000000000000000000000000000000"

# Function to validate a block
def validate_block(block, utxo_set):
    # Verify coinbase transaction
    coinbase_tx = block["coinbase_transaction"]
    if coinbase_tx["value"] != MINER_REWARD:
        return False
    # Additional validation for coinbase transaction if needed

    # Verify all transactions
    for tx in block["transactions"]:
        if not validate_transaction(tx, utxo_set):
            return False

    return True

# Function to validate a transaction
def validate_transaction(transaction, utxo_set):
    # Check that the sum of input values is >= the sum of output values
    input_sum = sum([input["prevout"]["value"] for input in transaction["vin"]])
    output_sum = sum([output["value"] for output in transaction["vout"]])
    if input_sum < output_sum:
        return False

    # Check that each input refers to an existing UTXO
    for input in transaction["vin"]:
        if input["prevout"]["scriptpubkey_address"] not in utxo_set:
            return False

    # Check that the transaction is correctly signed by the sender
    for input in transaction["vin"]:
        witness = input["witness"]
        if not verify_witness(witness, transaction):
            return False

    return True

# Function to verify the witness (signature)
def verify_witness(witness, transaction):
    # Extract signature and public key from witness
    signature_hex = witness[0]
    public_key_hex = witness[1]
    
    # Convert signature and public key to bytes
    signature = binascii.unhexlify(signature_hex)
    public_key = binascii.unhexlify(public_key_hex)
    
    # Extract message from the transaction data
    transaction_data = json.dumps(transaction, sort_keys=True)
    message = hashlib.sha256(transaction_data.encode()).digest()
    
    # Construct a signature object
    signature_obj = ecdsa.util.sigdecode_der(signature, ecdsa.SECP256k1)

    # Construct a public key object
    key = ecdsa.VerifyingKey.from_string(public_key, curve=ecdsa.SECP256k1)
    
    # Verify the signature
    return key.verify(signature_obj, message)

# Function to construct a block
def construct_block(transactions, utxo_set):
    block = {
        "transactions": [],
        "coinbase_transaction": {}  # Placeholder for coinbase transaction
    }
    block_size = 0
    
    # Include transactions until block size limit is reached
    for tx in transactions:
        if validate_transaction(tx, utxo_set) and block_size + len(json.dumps(tx)) <= MAX_BLOCK_SIZE:
            block["transactions"].append(tx)
            block_size += len(json.dumps(tx))
            # Remove transaction inputs from UTXO set
            for input in tx["vin"]:
                utxo_set.remove(input["prevout"]["scriptpubkey_address"])
    
    # Generate and include coinbase transaction
    coinbase_tx = generate_coinbase_transaction()
    block["coinbase_transaction"] = coinbase_tx
    
    return block

# Function to generate a coinbase transaction
def generate_coinbase_transaction():
    coinbase_tx = {
        "txid": "coinbase_tx_id",
        "vin": [],
        "vout": [
            {
                "value": MINER_REWARD,
                "scriptpubkey": "scriptpubkey_value"
            }
        ]
    }
    return coinbase_tx

# Function to mine a block
def mine_block(block, nonce_start, nonce_end):
    block_hash = ""
    nonce = nonce_start
    
    # Continue mining until block hash meets difficulty target or nonce end is reached
    while not block_hash.startswith(TARGET_DIFFICULTY) and nonce < nonce_end:
        # Update nonce and recalculate block hash
        block["nonce"] = nonce
        block_serialized = json.dumps(block, sort_keys=True)
        block_hash = hashlib.sha256(block_serialized.encode()).hexdigest()
        nonce += 1
    
    return block_hash, nonce

# Function to mine a block in parallel
def mine_block_parallel(block):
    # Create a pool of processes
    pool = multiprocessing.Pool(processes=NUM_PROCESSES)
    
    # Divide the nonce range among the processes
    nonce_range = range(0, 2**32)  # 32-bit nonce
    nonce_ranges = numpy.array_split(nonce_range, NUM_PROCESSES)
    
    # Start the processes
    results = [pool.apply_async(mine_block, args=(block, nonce_start, nonce_end)) for nonce_start, nonce_end in nonce_ranges]
    
    # Wait for the first process to find a valid block hash
    for result in multiprocessing.as_completed(results):
        block_hash, nonce = result.get()
        if block_hash.startswith(TARGET_DIFFICULTY):
            # Stop the other processes
            pool.terminate()
            return block_hash, nonce

    return None, None

# Initialize UTXO set
utxo_set = set()

# Read transactions from mempool folder
mempool_files = os.listdir(MEMPOOL_DIR)

transactions = []
for filename in mempool_files:
    with open(os.path.join(MEMPOOL_DIR, filename), "r") as file:
        transaction = json.load(file)
        transactions.append(transaction)
        # Add transaction outputs to UTXO set
        for output in transaction["vout"]:
            utxo_set.add(output["scriptpubkey_address"])

# Construct a block
block = construct_block(transactions, utxo_set)

# Mine the block in parallel
block_hash, nonce = mine_block_parallel(block)

# Verify the mined block
if block_hash is not None and nonce is not None:
    block["nonce"] = nonce
    block["hash"] = block_hash
    if validate_block(block, utxo_set):
        # Write output to output.txt
        with open("output.txt", "w") as output_file:
            output_file.write(block_hash + "\n")
            output_file.write(json.dumps(block["coinbase_transaction"]) + "\n")
            for tx in block["transactions"]:
                output_file.write(tx["txid"] + "\n")
    else:
        print("Mined block is not valid.")
else:
    print("Failed to mine a valid block.")
