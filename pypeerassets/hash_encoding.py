# Module to bundle address/hashlock encoding features.
# Segwit and Taproot still not implemented.
# Note: Protobuf needs bytes object (not bytearray), so both hash_to_addres and address_to_hash use bytes objects too.

from btcpy.structs.address import Address, P2pkhAddress, P2shAddress
from btcpy.structs.script import P2pkhScript, P2shScript

# for example: HASHTYPE[1] => p2pk
HASHTYPE = ( "hashlock", "p2pk", "p2pkh", "p2sh", "p2wpkh", "p2wsh", "p2tr" )

def hash_to_address(h: bytes, hash_type: int, network: object):
    if hash_type == 0:
        return None # hashlocks can't be encoded into addresses.
    elif hash_type > 3:
        raise NotImplementedError
    elif hash_type == 1:
        return NotImplementedError # P2PK anyway should be regarded as obsolete and discouraged.
    elif hash_type == 2:
        script = P2pkhScript(bytearray(h))
        return P2pkhAddress.from_script(script, network).__str__()
    elif hash_type == 3:
        script = P2shScript(bytearray(h))
        return P2shAddress.from_script(script, network).__str__()

def address_to_hash(a: str, hash_type: int, network: object):
    if hash_type == 0:
        return None
    elif hash_type > 3:
        raise NotImplementedError
    elif hash_type == 1:
        return NotImplementedError
    elif hash_type in (2, 3):
        addr = Address.from_string(a, network)
        return bytes(addr.hash)





