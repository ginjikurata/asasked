"""A minimal Solana client for the crypto payment demo: keys, transactions, devnet RPC.

Only what the demo needs, written against the wire format so the package
gains no dependency: base58, ed25519 keys (the cryptography package the
project already uses), program-derived addresses, legacy transactions and
the handful of System, SPL Token, Associated Token Account and Memo
instructions that create a test token and move it.

This is for devnet, where tokens are worthless. Rpc refuses a URL that
names mainnet, and before its first transaction it asks the cluster for its
genesis hash and refuses mainnet's, so a demo wallet cannot be pointed at
real money by mistake. Do not reuse this module for mainnet: it has no priority fees,
retries or simulation beyond the RPC's preflight.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

DEVNET_URL = "https://api.devnet.solana.com"
EXPLORER_TX = "https://explorer.solana.com/tx/{}?cluster=devnet"
EXPLORER_ADDRESS = "https://explorer.solana.com/address/{}?cluster=devnet"
MAINNET_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"

# ---------------------------------------------------------------------------
# base58
# ---------------------------------------------------------------------------

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text:
        i = _B58.find(ch)
        if i < 0:
            raise ValueError(f"not base58: {text!r}")
        n = n * 58 + i
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + body


def pubkey(address: str) -> bytes:
    """A base58 address -> its 32 bytes; anything else is an error."""
    raw = b58decode(address)
    if len(raw) != 32:
        raise ValueError(f"not a Solana address: {address!r}")
    return raw


SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

# ---------------------------------------------------------------------------
# Keys and addresses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Keypair:
    secret: bytes          # the 32-byte ed25519 seed

    @classmethod
    def generate(cls) -> Keypair:
        return cls(os.urandom(32))

    @classmethod
    def from_seed_phrase(cls, phrase: str) -> Keypair:
        """A deterministic key from text: for simulated wallets and tests only."""
        return cls(hashlib.sha256(phrase.encode()).digest())

    @classmethod
    def load(cls, path: str) -> Keypair:
        """A key file in the Solana CLI format: a JSON list of 64 bytes."""
        with open(path) as f:
            data = bytes(json.load(f))
        if len(data) != 64:
            raise ValueError(f"{path}: expected 64 bytes")
        key = cls(data[:32])
        if key.public != data[32:]:
            raise ValueError(f"{path}: the public half does not match the secret")
        return key

    def save(self, path: str) -> None:
        # Created with owner-only permissions: it is a key, if a worthless one.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(list(self.secret + self.public), f)

    @property
    def public(self) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(self.secret).public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw)

    @property
    def address(self) -> str:
        return b58encode(self.public)

    def sign(self, message: bytes) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(self.secret).sign(message)


_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def on_curve(key: bytes) -> bool:
    """Whether 32 bytes decode to an ed25519 point, as curve25519-dalek decides.

    A program-derived address must not: no private key can exist for it.
    """
    y = int.from_bytes(key, "little") & ((1 << 255) - 1)
    u = (y * y - 1) % _P
    v = (_D * y * y + 1) % _P
    x2 = u * pow(v, _P - 2, _P) % _P
    return x2 == 0 or pow(x2, (_P - 1) // 2, _P) == 1


def find_program_address(seeds: list[bytes], program: str) -> tuple[str, int]:
    program_id = pubkey(program)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + program_id
                           + b"ProgramDerivedAddress").digest()
        if not on_curve(h):
            return b58encode(h), bump
    raise ValueError("no program address found")


def token_account(owner: str, mint: str) -> str:
    """The owner's associated token account for a mint."""
    return find_program_address([pubkey(owner), pubkey(TOKEN_PROGRAM), pubkey(mint)],
                                ATA_PROGRAM)[0]

# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Meta:
    address: str
    signer: bool = False
    writable: bool = False


@dataclass(frozen=True)
class Instruction:
    program: str
    accounts: tuple[Meta, ...]
    data: bytes


def shortvec(n: int) -> bytes:
    """Solana's compact-u16 length prefix."""
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def compile_message(payer: str, instructions: list[Instruction], blockhash: str) -> bytes:
    """A legacy transaction message: header, accounts, blockhash, instructions."""
    flags: dict[str, list[bool]] = {payer: [True, True]}
    for ix in instructions:
        for m in ix.accounts:
            f = flags.setdefault(m.address, [False, False])
            f[0] |= m.signer
            f[1] |= m.writable
        flags.setdefault(ix.program, [False, False])
    # Order: writable signers (payer first), read-only signers, writable others, read-only others.
    keys = sorted(flags, key=lambda a: (a != payer, not flags[a][0], not flags[a][1]))
    signed = [a for a in keys if flags[a][0]]
    header = bytes([len(signed),
                    sum(1 for a in signed if not flags[a][1]),
                    sum(1 for a in keys if not flags[a][0] and not flags[a][1])])
    index = {a: i for i, a in enumerate(keys)}
    body = bytearray(header + shortvec(len(keys)) + b"".join(pubkey(a) for a in keys)
                     + pubkey(blockhash) + shortvec(len(instructions)))
    for ix in instructions:
        body += bytes([index[ix.program]])
        body += shortvec(len(ix.accounts)) + bytes(index[m.address] for m in ix.accounts)
        body += shortvec(len(ix.data)) + ix.data
    return bytes(body)


def sign_transaction(message: bytes, signers: list[Keypair]) -> bytes:
    """The wire transaction: every required signature, in account order, then the message."""
    required, count = message[0], message[3]
    if count >= 0x80:                               # a one-byte shortvec: under 128 accounts
        raise ValueError("too many accounts for this demo client")
    keys = message[4:4 + 32 * count]
    order = [b58encode(keys[i * 32:(i + 1) * 32]) for i in range(required)]
    by_address = {k.address: k for k in signers}
    missing = [a for a in order if a not in by_address]
    if missing:
        raise ValueError(f"missing signatures for {missing}")
    return shortvec(required) + b"".join(by_address[a].sign(message) for a in order) + message


# Instructions -------------------------------------------------------------

def create_account(payer: str, new: str, lamports: int, space: int, owner: str) -> Instruction:
    return Instruction(SYSTEM_PROGRAM, (Meta(payer, True, True), Meta(new, True, True)),
                       struct.pack("<IQQ", 0, lamports, space) + pubkey(owner))


def initialize_mint(mint: str, decimals: int, authority: str) -> Instruction:
    # InitializeMint2 (20): decimals, mint authority, no freeze authority.
    return Instruction(TOKEN_PROGRAM, (Meta(mint, False, True),),
                       bytes([20, decimals]) + pubkey(authority) + b"\0")


def create_token_account(payer: str, owner: str, mint: str) -> Instruction:
    # CreateIdempotent (1): does nothing if the account is already there.
    return Instruction(ATA_PROGRAM, (
        Meta(payer, True, True), Meta(token_account(owner, mint), False, True),
        Meta(owner), Meta(mint), Meta(SYSTEM_PROGRAM), Meta(TOKEN_PROGRAM)), b"\1")


def mint_to(mint: str, owner: str, authority: str, amount: int) -> Instruction:
    return Instruction(TOKEN_PROGRAM, (
        Meta(mint, False, True), Meta(token_account(owner, mint), False, True),
        Meta(authority, True)), bytes([7]) + struct.pack("<Q", amount))


def transfer_checked(mint: str, sender: str, recipient: str, amount: int,
                     decimals: int) -> Instruction:
    """Moves amount base units from the sender's token account to the recipient's."""
    return Instruction(TOKEN_PROGRAM, (
        Meta(token_account(sender, mint), False, True), Meta(mint),
        Meta(token_account(recipient, mint), False, True), Meta(sender, True)),
        bytes([12]) + struct.pack("<QB", amount, decimals))


def memo(text: str) -> Instruction:
    return Instruction(MEMO_PROGRAM, (), text.encode())

# ---------------------------------------------------------------------------
# RPC
# ---------------------------------------------------------------------------


class RpcError(Exception):
    """The RPC or the cluster refused: nothing was sent, or the transaction failed."""


class OutcomeUnknown(RpcError):
    """A transaction may or may not land. Do not send it again: look it up first."""

    def __init__(self, message: str, signature: str):
        super().__init__(message)
        self.signature = signature


class Rpc:
    def __init__(self, url: str = DEVNET_URL, timeout: float = 30):
        if "mainnet" in url:
            raise ValueError("this demo client works on devnet only")
        self.url, self.timeout, self._id = url, timeout, 0
        self._cluster_checked = False

    def call(self, method: str, *params):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method,
                           "params": list(params)}).encode()
        request = urllib.request.Request(self.url, body,
                                         {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as e:
            body = e.read()[:2000]
            try:
                detail = json.loads(body)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                detail = body[:300].decode(errors="replace").strip()
            raise RpcError(f"{method}: HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RpcError(f"{method}: {e.reason}") from e
        if "error" in reply:
            raise RpcError(f"{method}: {reply['error'].get('message', reply['error'])}")
        return reply["result"]

    def blockhash(self) -> tuple[str, int]:
        """The latest blockhash and the last block height a transaction using it can land in."""
        value = self.call("getLatestBlockhash", {"commitment": "confirmed"})["value"]
        return value["blockhash"], value["lastValidBlockHeight"]

    def check_cluster(self) -> None:
        """Refuses mainnet by its genesis hash, whatever the URL says. Asked once."""
        if not self._cluster_checked:
            if self.call("getGenesisHash") == MAINNET_GENESIS:
                raise ValueError("this demo client works on devnet only; this RPC is mainnet")
            self._cluster_checked = True

    def balance(self, address: str) -> int:
        return self.call("getBalance", address, {"commitment": "confirmed"})["value"]

    def token_balance(self, owner: str, mint: str) -> int:
        """Base units in the owner's token account; 0 if it does not exist yet."""
        try:
            value = self.call("getTokenAccountBalance", token_account(owner, mint),
                              {"commitment": "confirmed"})["value"]
        except RpcError as e:
            if "could not find account" in str(e).lower() or "invalid param" in str(e).lower():
                return 0
            raise
        return int(value["amount"])

    def exists(self, address: str) -> bool:
        return self.call("getAccountInfo", address,
                         {"encoding": "base64", "commitment": "confirmed"})["value"] is not None

    def rent(self, space: int) -> int:
        return self.call("getMinimumBalanceForRentExemption", space)

    def airdrop(self, address: str, lamports: int) -> str:
        self.check_cluster()
        return self.call("requestAirdrop", address, lamports, {"commitment": "confirmed"})

    def send(self, payer: Keypair, instructions: list[Instruction],
             extra_signers: tuple[Keypair, ...] = ()) -> str:
        """Signs, sends and waits for confirmation; returns the signature.

        RpcError means the transaction did not and will not happen.
        OutcomeUnknown means it may still land: the request to send it or the
        wait for it broke off. Its signature is known either way (it is the
        payer's signature), so it can be looked up, and must not be resent.
        """
        self.check_cluster()
        blockhash, last_valid = self.blockhash()
        message = compile_message(payer.address, instructions, blockhash)
        tx = sign_transaction(message, [payer, *extra_signers])
        signature = b58encode(tx[1:65])
        try:
            sent = self.call("sendTransaction", base64.b64encode(tx).decode(),
                             {"encoding": "base64", "preflightCommitment": "confirmed"})
        except RpcError as e:
            if e.__cause__ is None:
                raise                       # the node answered with an error: refused
            raise OutcomeUnknown(f"sending {signature}: {e}", signature) from e
        except (OSError, ValueError) as e:  # cut off mid-reply, or an unreadable reply
            raise OutcomeUnknown(f"sending {signature}: {e!r}", signature) from e
        if sent != signature:
            raise OutcomeUnknown(f"the RPC returned {sent} for {signature}", signature)
        self.confirm(signature, last_valid)
        return signature

    def _status(self, signature: str) -> tuple[bool, dict | None]:
        """(whether the RPC answered, the transaction's status or None)."""
        try:
            return True, self.call("getSignatureStatuses", [signature],
                                   {"searchTransactionHistory": True})["value"][0]
        except (RpcError, OSError, ValueError):
            return False, None

    def confirm(self, signature: str, last_valid: int | None = None,
                timeout: float = 90) -> None:
        """Waits until the transaction is confirmed.

        RpcError if it failed, or if the chain has passed last_valid (its
        blockhash expired, so it can no longer land). OutcomeUnknown if the
        wait ran out first.
        """
        deadline = time.monotonic() + timeout
        while True:
            answered, status = self._status(signature)
            if status:
                if status.get("err"):
                    raise RpcError(f"transaction {signature} failed: {status['err']}")
                if status.get("confirmationStatus") in ("confirmed", "finalized"):
                    return
            elif answered and last_valid is not None:
                try:
                    height = self.call("getBlockHeight", {"commitment": "confirmed"})
                except (RpcError, OSError, ValueError):
                    height = None
                if height is not None and height > last_valid:
                    # one more look: it may have landed just before the height passed
                    answered, status = self._status(signature)
                    if answered and not status:
                        raise RpcError(f"transaction {signature} expired without landing")
                    if status:
                        continue
            if time.monotonic() >= deadline:
                raise OutcomeUnknown(f"transaction {signature} not confirmed in "
                                     f"{timeout:.0f}s; it may still land", signature)
            time.sleep(1)


__all__ = [
    "ATA_PROGRAM", "DEVNET_URL", "EXPLORER_ADDRESS", "EXPLORER_TX", "Instruction", "Keypair",
    "MAINNET_GENESIS", "MEMO_PROGRAM", "Meta", "OutcomeUnknown", "Rpc", "RpcError",
    "SYSTEM_PROGRAM", "TOKEN_PROGRAM",
    "b58decode", "b58encode", "compile_message", "create_account", "create_token_account",
    "find_program_address", "initialize_mint", "memo", "mint_to", "on_curve", "pubkey",
    "shortvec", "sign_transaction", "token_account", "transfer_checked",
]
