import pytest
from pypeerassets.networks import net_query

from pypeerassets.hash_encoding import hash_to_address, address_to_hash

def test_hash_to_address():
    network_params = net_query("tslm")
    hex_h = "418bc8cbe0ffd20cc7cf0caaa98f6e58d90e1d59" # c9172582e208aeae79bdcb903489c7f9fb886434
    h = bytes.fromhex(hex_h)
    address = hash_to_address(h, 2, network_params)
    assert address == "mmVXfumjbbra6j8H26wRQEZA4u9dEHQNwN" # myrDqrtPcqJzPKzsKp5UxFokFfk3KW3sir

def test_address_to_hash():
    network_params = net_query("tslm")
    address = "mmVXfumjbbra6j8H26wRQEZA4u9dEHQNwN"
    h = address_to_hash(address, 2, network_params)
    assert h == b'A\x8b\xc8\xcb\xe0\xff\xd2\x0c\xc7\xcf\x0c\xaa\xa9\x8fnX\xd9\x0e\x1dY' # bytes value of hex: 418bc8cbe0ffd20cc7cf0caaa98f6e58d90e1d59

