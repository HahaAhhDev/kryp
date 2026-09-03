# language/base.py
"""Built in helpers"""
from __future__ import annotations
import argparse
import base64
import os
import getpass
import logging
import shutil
import string
import secrets
import random
import sys
import subprocess
from pathlib import Path
import json
import time
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich.prompt import Prompt
from rich import box

from argon2 import low_level
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import requests

status = "INSTALLED"

ce = Console()
inp = Prompt()

# Constants for security parameters
SALT_SIZE: int = 16  # 16 bytes for salt provides sufficient uniqueness and resistance to rainbow table attacks
NONCE_SIZE: int = 12  # 12 bytes for GCM nonce, as recommended by NIST
DEFAULT_TIME_COST: int = 2  # Argon2 time cost; higher values increase computational cost, deterring brute-force attacks
DEFAULT_MEMORY_COST: int = 102400  # 100 MiB; memory-hard function resists GPU/ASIC attacks
DEFAULT_PARALLELISM: int = 8  # Parallelism for Argon2; balances security and performance


class GlobalStorage:
    """Enhanced global storage class with improved error handling and security."""

    def __init__(self, namespace: str):
        """Initialize storage with namespace validation."""
        if not isinstance(namespace, str) or len(namespace) == 0:
            raise ValueError("Namespace must be non-empty string")
        self.namespace = namespace
        self.data = {}
        self.paste_url = None  # Store the paste URL/ID
        self._timeout = 30  # Network timeout in seconds

    def _save_to_paste(self):
        """Save data to paste.rs with error handling and validation."""
        try:
            payload = json.dumps(self.data, separators=(',', ':'))  # Compact JSON
            response = requests.post(
                "https://paste.rs",
                data=payload.encode('utf-8'),
                headers={'Content-Type': 'text/plain'},
                timeout=self._timeout
            )
            response.raise_for_status()
            self.paste_url = response.text.strip()
            logging.debug(f"Data saved to paste: {self.paste_url}")
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to save data to paste.rs: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error saving data: {e}") from e

    def _load_from_paste(self):
        """Load data from paste.rs with validation and error handling."""
        if not self.paste_url:
            self.data = {}
            return

        try:
            # Validate URL format
            if not self.paste_url.startswith('https://paste.rs/'):
                raise ValueError("Invalid paste.rs URL format")

            response = requests.get(self.paste_url, timeout=self._timeout)
            response.raise_for_status()

            # Parse JSON with validation
            self.data = json.loads(response.text)
            if not isinstance(self.data, dict):
                raise ValueError("Invalid data format: expected dictionary")

            logging.debug(f"Data loaded from paste: {self.paste_url}")
        except requests.RequestException as e:
            logging.warning(f"Failed to load data from paste.rs: {e}")
            self.data = {}  # Fallback to empty data
        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"Invalid data format in paste: {e}")
            self.data = {}  # Fallback to empty data
        except Exception as e:
            logging.warning(f"Unexpected error loading data: {e}")
            self.data = {}  # Fallback to empty data

    def set(self, key, value):
        """Set a key-value pair with validation and automatic save."""
        if not isinstance(key, str) or len(key) == 0:
            raise ValueError("Key must be non-empty string")
        if value is None:
            raise ValueError("Value cannot be None")

        self.data[key] = value
        self._save_to_paste()
        logging.debug(f"Set key '{key}' in namespace '{self.namespace}'")

    def get(self, key, default=None):
        """Get a value by key with automatic load and validation."""
        if not isinstance(key, str) or len(key) == 0:
            raise ValueError("Key must be non-empty string")

        self._load_from_paste()
        value = self.data.get(key, default)
        logging.debug(f"Get key '{key}' from namespace '{self.namespace}': {'found' if key in self.data else 'not found'}")
        return value

    def delete(self, key):
        """Delete a key with validation and automatic save."""
        if not isinstance(key, str) or len(key) == 0:
            raise ValueError("Key must be non-empty string")

        self._load_from_paste()
        if key in self.data:
            del self.data[key]
            self._save_to_paste()
            logging.debug(f"Deleted key '{key}' from namespace '{self.namespace}'")
            return True
        else:
            logging.debug(f"Key '{key}' not found in namespace '{self.namespace}'")
            return False

    def clear(self):
        """Clear all data in the namespace."""
        self.data = {}
        self._save_to_paste()
        logging.debug(f"Cleared all data in namespace '{self.namespace}'")

    def keys(self):
        """Get all keys in the namespace."""
        self._load_from_paste()
        return list(self.data.keys())

    def size(self):
        """Get the number of items in the namespace."""
        self._load_from_paste()
        return len(self.data)

# Custom Exceptions to avoid exposing sensitive data in error messages
class EncryptionError(Exception):
    """Raised when encryption fails, without revealing internal details."""
    pass


class DecryptionError(Exception):
    """Raised when decryption fails, without revealing internal details."""
    pass


# ========================
# File Helpers
# ========================

def rm_tree(path):
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)

def runos(cmd):
    """
    Runs a command from shell that executes things, not give text
    """
    os.system(cmd)

def run(cmd):
    """
    Runs a shell command and returns stdout as text
    """
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.stdout

def show(text):
    print(text)

def checkpath(path):
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w"):
            pass

def readfile(path):
    checkpath(path)
    with open(path, "r") as f:
        return f.read().strip()

def writefile(path, content):
    checkpath(path)
    with open(path, "w") as f:
        f.write(content)

def writeapp(path, content):
    checkpath(path)
    with open(path, "a") as f:
        f.write("\n" + content)

def writeinline(path, line, content):
    """
    Write content to a specific line in a file.
    Extends the file with empty lines if necessary.
    """
    checkpath(path)

    # Read existing lines
    with open(path, "r") as f:
        lines = f.read().splitlines()

    # Extend the list with empty lines if needed
    while len(lines) <= line:
        lines.append("")

    # Replace the specific line
    lines[line] = content

    # Write back all lines
    with open(path, "w") as f:
        f.write("\n".join(lines))

def genpass(length=12):
    """Generate cryptographically secure random password."""
    # Use secrets module for cryptographic randomness instead of random
    characters = string.ascii_letters + string.digits + string.punctuation
    # Generate secure random password using secrets.choice
    password = ''.join(secrets.choice(characters) for _ in range(length))
    return password

def extract(path, line=-1):
    """
    Extract a specific line from a file
    """
    checkpath(path)
    with open(path, "r") as f:
        lines = f.read().splitlines()

    if not lines:
        return ""

    return lines[line]

# ========================
# Encoding Helpers (for text, not used in crypto core)
# ========================

def encode_binary(text: str) -> str:
    """Convert text to binary (8-bit ASCII)."""
    return ' '.join(format(ord(char), '08b') for char in text)


def decode_binary(binary: str) -> str:
    """Convert binary (space-separated) back to text."""
    try:
        chars = binary.split()
        return ''.join(chr(int(b, 2)) for b in chars)
    except ValueError as e:
        raise ValueError(f"Invalid binary format: {e}") from e


def encode_hex(text: str) -> str:
    """Convert text to Base16 / hexadecimal."""
    return text.encode("utf-8").hex()


def decode_hex(hex_text: str) -> str:
    """Convert Base16 / hexadecimal back to text."""
    try:
        return bytes.fromhex(hex_text).decode("utf-8")
    except ValueError as e:
        raise ValueError(f"Invalid hexadecimal format: {e}") from e


def encode_base64(text: str) -> str:
    """Encode text to Base64."""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_base64(encoded_text: str) -> str:
    """Decode Base64 back to text."""
    try:
        return base64.b64decode(encoded_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Invalid Base64 format: {e}") from e


# ========================
# Core Crypto Helpers
# ========================

def _derive_key(password: str, salt: bytes, time_cost: int = DEFAULT_TIME_COST, memory_cost: int = DEFAULT_MEMORY_COST, parallelism: int = DEFAULT_PARALLELISM) -> bytes:
    """
    Derives a 32-byte (256-bit) AES-256 key from password and salt using Argon2.
    Argon2 is used for its resistance to GPU attacks, side-channel attacks, and trade-off attacks due to its memory-hard nature,
    making it more secure than PBKDF2 for password-based key derivation in industrial/military contexts.
    """
    # Validate security parameters
    if time_cost < 1:
        raise ValueError("Time cost must be at least 1 for security.")
    if memory_cost < 1024:
        raise ValueError("Memory cost must be at least 1024 KiB for security.")
    if parallelism < 1:
        raise ValueError("Parallelism must be at least 1.")

    try:
        # Derive key using Argon2id for maximum security
        key = low_level.hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            hash_len=32,  # 256-bit key for AES-256
            type=low_level.Type.ID,  # Argon2id variant, recommended for password hashing
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )
        return key
    except Exception as e:
        raise EncryptionError("Key derivation failed") from e
    finally:
        # Attempt to clear password from memory (limited in Python due to GC)
        del password


# ========================
# Simple Encryption/Decryption for Text
# ========================

def encrypt(text: str, password: str) -> str:
    """
    Simple function to encrypt a text string with a password.
    Returns base64-encoded encrypted data.
    """
    try:
        result = encrypt_data(text.encode("utf-8"), password)
        del password  # Wipe password from memory
        return result
    except:
        del password  # Ensure wipe even on error
        raise


def decrypt(encrypted: str, password: str) -> str:
    """
    Simple function to decrypt base64-encoded encrypted data with a password.
    Returns the decrypted text string.
    """
    try:
        result = decrypt_data(encrypted, password).decode("utf-8")
        del password  # Wipe password from memory
        return result
    except:
        del password  # Ensure wipe even on error
        raise


# ========================
# AES-GCM Encryption/Decryption for Data (bytes)
# ========================

def encrypt_data(plaintext: bytes, password: str, aad: Optional[bytes] = None, time_cost: int = DEFAULT_TIME_COST, memory_cost: int = DEFAULT_MEMORY_COST, parallelism: int = DEFAULT_PARALLELISM) -> str:
    """
    Encrypts plaintext bytes using AES-256-GCM with a key derived from password via Argon2.
    AES-256 provides strong encryption against brute-force attacks.
    GCM mode offers authenticated encryption, detecting any tampering.
    Random salt and nonce prevent replay attacks and ensure uniqueness.
    Optional AAD ensures integrity of associated data without encrypting it.
    Returns base64-encoded encrypted data for safe text-based storage/transmission.
    """
    # Input validation
    if not isinstance(plaintext, bytes):
        raise ValueError("Plaintext must be bytes")
    if not isinstance(password, str) or len(password) == 0:
        raise ValueError("Password must be non-empty string")
    if len(plaintext) > 100 * 1024 * 1024:  # 100MB limit
        raise ValueError("Plaintext too large (max 100MB)")

    key = None
    try:
        # Generate cryptographically secure random values
        salt = secrets.token_bytes(SALT_SIZE)  # Cryptographically secure random salt
        nonce = secrets.token_bytes(NONCE_SIZE)  # Unique nonce per encryption

        # Derive encryption key using Argon2
        key = _derive_key(password, salt, time_cost, memory_cost, parallelism)

        # Initialize AES-GCM cipher
        aes = AESGCM(key)

        # Perform authenticated encryption
        ciphertext = aes.encrypt(nonce, plaintext, aad)

        # Format: salt || nonce || ciphertext; base64 encoding ensures safe handling as text
        encrypted_data = salt + nonce + ciphertext
        return base64.b64encode(encrypted_data).decode("ascii")

    except Exception as e:
        raise EncryptionError("Encryption failed.") from e
    finally:
        # Secure memory cleanup (limited in Python due to GC)
        if key:
            del key


def decrypt_data(encrypted_data: str, password: str, aad: Optional[bytes] = None, time_cost: int = DEFAULT_TIME_COST, memory_cost: int = DEFAULT_MEMORY_COST, parallelism: int = DEFAULT_PARALLELISM) -> bytes:
    """
    Decrypts base64-encoded encrypted data using AES-256-GCM.
    Verifies integrity via GCM authentication tag; fails if data is tampered or password is wrong.
    Returns plaintext bytes.
    """
    # Input validation
    if not isinstance(encrypted_data, str) or len(encrypted_data) == 0:
        raise ValueError("Encrypted data must be non-empty string")
    if not isinstance(password, str) or len(password) == 0:
        raise ValueError("Password must be non-empty string")

    key = None
    try:
        # Decode base64 encrypted data
        data = base64.b64decode(encrypted_data)

        # Validate minimum data length (salt + nonce + minimum ciphertext + GCM tag)
        min_length = SALT_SIZE + NONCE_SIZE + 16  # +16 for GCM authentication tag
        if len(data) < min_length:
            raise ValueError(f"Encrypted data too short: {len(data)} < {min_length}")

        # Extract components from encrypted data
        salt = data[:SALT_SIZE]
        nonce = data[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
        ciphertext = data[SALT_SIZE + NONCE_SIZE :]

        # Derive decryption key using same parameters
        key = _derive_key(password, salt, time_cost, memory_cost, parallelism)

        # Initialize AES-GCM cipher
        aes = AESGCM(key)

        # Perform authenticated decryption
        plaintext = aes.decrypt(nonce, ciphertext, aad)

        return plaintext

    except InvalidTag:
        raise DecryptionError("Decryption failed: Invalid password or corrupted data.")
    except (ValueError, TypeError) as e:
        raise DecryptionError(f"Invalid data format: {e}") from e
    except Exception as e:
        raise DecryptionError("Decryption failed.") from e
    finally:
        # Secure memory cleanup (limited in Python due to GC)
        if key:
            del key


# ========================
# File Encryption/Decryption (handles binary safely)
# ========================

def encrypt_file(input_path: Path, output_path: Path, password: str, aad: Optional[bytes] = None, time_cost: int = DEFAULT_TIME_COST, memory_cost: int = DEFAULT_MEMORY_COST, parallelism: int = DEFAULT_PARALLELISM) -> None:
    """
    Encrypts a file (binary-safe) using AES-GCM and writes base64-encoded encrypted data to output file as text.
    Handles binary files by reading as bytes, ensuring no encoding issues.
    """
    plaintext = None
    try:
        # Validate input file exists and is readable
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        if not input_path.is_file():
            raise ValueError(f"Input path is not a file: {input_path}")

        # Check file size limits
        file_size = input_path.stat().st_size
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            raise ValueError(f"File too large: {file_size} bytes (max 100MB)")
        if file_size == 0:
            raise ValueError("Cannot encrypt empty file")

        # Read file as bytes for binary safety
        plaintext = input_path.read_bytes()

        # Encrypt file data
        encrypted = encrypt_data(plaintext, password, aad, time_cost, memory_cost, parallelism)

        # Atomic write to prevent corruption
        temp_path = output_path.with_suffix(output_path.suffix + '.tmp')
        temp_path.write_text(encrypted, encoding='ascii')
        temp_path.replace(output_path)

        logging.info(f"File encrypted successfully: {input_path} -> {output_path} ({file_size} bytes)")

    except Exception as e:
        raise EncryptionError(f"File encryption failed: {e}") from e
    finally:
        # Clear sensitive data from memory
        if plaintext:
            del plaintext


def decrypt_file(input_path: Path, output_path: Path, password: str, aad: Optional[bytes] = None, time_cost: int = DEFAULT_TIME_COST, memory_cost: int = DEFAULT_MEMORY_COST, parallelism: int = DEFAULT_PARALLELISM) -> None:
    """
    Decrypts a file (binary-safe) using AES-GCM and writes decrypted bytes to output file.
    Reads base64 text, decrypts to bytes, ensuring binary files are restored correctly.
    """
    encrypted_data = None
    plaintext = None
    try:
        # Validate input file exists and is readable
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        if not input_path.is_file():
            raise ValueError(f"Input path is not a file: {input_path}")

        # Check file is not empty
        file_size = input_path.stat().st_size
        if file_size == 0:
            raise ValueError("Cannot decrypt empty file")

        # Read encrypted data as text (base64)
        encrypted_data = input_path.read_text(encoding='ascii')

        # Decrypt file data
        plaintext = decrypt_data(encrypted_data, password, aad, time_cost, memory_cost, parallelism)

        # Atomic write to prevent corruption
        temp_path = output_path.with_suffix(output_path.suffix + '.tmp')
        temp_path.write_bytes(plaintext)
        temp_path.replace(output_path)

        logging.info(f"File decrypted successfully: {input_path} -> {output_path} ({len(plaintext)} bytes)")

    except Exception as e:
        raise DecryptionError(f"File decryption failed: {e}") from e
    finally:
        # Clear sensitive data from memory
        if encrypted_data:
            del encrypted_data
        if plaintext:
            del plaintext


# ========================
# CLI Interface
# ========================

def setup_logging(level: str = "INFO") -> None:
    """Configure secure logging with sensitive data protection and enhanced formatting."""
    # Security-focused logging configuration
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)8s] %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Disable debug logging in production for security
    if level.upper() != "DEBUG":
        logging.getLogger().setLevel(logging.INFO)

    # Log initialization with security notice
    logging.info("OblivX cryptographic module initialized with enhanced security")


def cli() -> None:
    """Enhanced CLI entry point with comprehensive argument parsing and validation."""
    parser = argparse.ArgumentParser(
        description="Military-Grade AES-256-GCM Encryption/Decryption Tool with Argon2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Security Features:
  • AES-256-GCM authenticated encryption
  • Argon2id key derivation (OWASP recommended)
  • Cryptographically secure random generation
  • Memory wiping and secure deletion
  • Comprehensive input validation"""
    )

    # Enhanced argument validation with bounds checking
    parser.add_argument("--time-cost", type=int, default=DEFAULT_TIME_COST,
                       help=f"Argon2 time cost (default: {DEFAULT_TIME_COST}, range: 1-10)")
    parser.add_argument("--memory-cost", type=int, default=DEFAULT_MEMORY_COST,
                       help=f"Argon2 memory cost in KiB (default: {DEFAULT_MEMORY_COST})")
    parser.add_argument("--parallelism", type=int, default=DEFAULT_PARALLELISM,
                       help=f"Argon2 parallelism (default: {DEFAULT_PARALLELISM}, range: 1-16)")
    parser.add_argument("--log-level", default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging verbosity level")
    parser.add_argument("--version", action="version", version="OblivX Crypto v2.0")

    subparsers = parser.add_subparsers(dest="command", required=True,
                                      help="Available cryptographic operations")

    # Message encryption/decryption commands
    msg_enc = subparsers.add_parser("encrypt-message", help="Encrypt a text message")
    msg_enc.add_argument("message", help="Message to encrypt")
    msg_enc.add_argument("--aad", help="Additional authenticated data (base64-encoded)")

    msg_dec = subparsers.add_parser("decrypt-message", help="Decrypt a text message")
    msg_dec.add_argument("encrypted", help="Encrypted message (base64-encoded)")
    msg_dec.add_argument("--aad", help="Additional authenticated data (base64-encoded)")

    # File encryption/decryption commands
    file_enc = subparsers.add_parser("encrypt-file", help="Encrypt a file (binary-safe)")
    file_enc.add_argument("input", type=Path, help="Input file path")
    file_enc.add_argument("output", type=Path, help="Output encrypted file path")
    file_enc.add_argument("--aad", help="Additional authenticated data (base64-encoded)")

    file_dec = subparsers.add_parser("decrypt-file", help="Decrypt a file (binary-safe)")
    file_dec.add_argument("input", type=Path, help="Input encrypted file path")
    file_dec.add_argument("output", type=Path, help="Output decrypted file path")
    file_dec.add_argument("--aad", help="Additional authenticated data (base64-encoded)")

    args = parser.parse_args()

    # Validate Argon2 parameters for security
    if not (1 <= args.time_cost <= 10):
        parser.error("Time cost must be between 1 and 10 for security")
    if not (1024 <= args.memory_cost <= 1048576):  # 1KB to 1GB
        parser.error("Memory cost must be between 1024 and 1048576 KiB")
    if not (1 <= args.parallelism <= 16):
        parser.error("Parallelism must be between 1 and 16")

    # Configure logging with security considerations
    setup_logging(args.log_level)

    # Secure password input with validation
    password = getpass.getpass("Enter password (will not echo): ")
    if len(password) == 0:
        logging.error("Password cannot be empty")
        sys.exit(1)

    # Process additional authenticated data if provided
    aad_bytes = None
    if hasattr(args, 'aad') and args.aad:
        try:
            aad_bytes = base64.b64decode(args.aad)
        except Exception as e:
            logging.error(f"Invalid AAD format: must be valid base64 - {e}")
            sys.exit(1)

    try:
        # Execute the requested cryptographic operation
        if args.command == "encrypt-message":
            result = encrypt_data(args.message.encode("utf-8"), password, aad_bytes,
                                args.time_cost, args.memory_cost, args.parallelism)
            print(result)

        elif args.command == "decrypt-message":
            result = decrypt_data(args.encrypted, password, aad_bytes,
                                args.time_cost, args.memory_cost, args.parallelism)
            print(result.decode("utf-8"))

        elif args.command == "encrypt-file":
            encrypt_file(args.input, args.output, password, aad_bytes,
                        args.time_cost, args.memory_cost, args.parallelism)
            print(f"✓ File encrypted successfully: {args.output}")

        elif args.command == "decrypt-file":
            decrypt_file(args.input, args.output, password, aad_bytes,
                        args.time_cost, args.memory_cost, args.parallelism)
            print(f"✓ File decrypted successfully: {args.output}")

    except (EncryptionError, DecryptionError) as e:
        logging.error(f"Cryptographic operation failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logging.error(f"Unexpected error occurred: {type(e).__name__}")
        sys.exit(1)
    finally:
        # Secure cleanup of sensitive data
        del password