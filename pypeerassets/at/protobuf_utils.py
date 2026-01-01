# utils to deal with protobuf. Preliminary. Will be probably divided in more files.
# maybe it's also good to use the Proto objects only here, so keep this file.

from .ttx_asd_pb2 import TrackedTransaction as TrackedTransactionProto, CardExtendedData as CardExtendedDataProto, DeckExtendedData as DeckExtendedDataProto
from pypeerassets.exceptions import OverSizeOPReturn

from pypeerassets.hash_encoding import address_to_hash
import pypeerassets.at.constants as c
from google.protobuf.message import DecodeError
from decimal import Decimal
from enum import Enum
import warnings


MESSAGES = {
           "card" : CardExtendedDataProto(),
           "deck" : DeckExtendedDataProto(),
           "ttx" : TrackedTransactionProto()
           }

def parse_protobuf(protobuf: bytes, msg_type: str, clean: bool=True, debug: bool=False) -> dict:

    data = MESSAGES[msg_type]

    try:
        warnings.filterwarnings("error", category=RuntimeWarning)
        data.ParseFromString(protobuf)
        warnings.resetwarnings()
    except DecodeError:
        raise ValueError("No protobuf string.")
    except RuntimeWarning as r:
        print("RuntimeWarning for message of type {}: {}".format(msg_type, r))
    except SystemError as s:
        if debug:
            print("SystemError: RuntimeWarning for message of type {}: {}".format(msg_type, s))
            print("Protobuf data with incorrect format. Will likely not be parsed correctly.")
    return protobuf_to_dict(data, clean)

def serialize_ttx_metadata(network: tuple, transaction: object=None, params: dict=None):

    tx = TrackedTransactionProto()

    if transaction is not None:
        params = transaction.__dict__
    elif params is None:
        raise ValueError("You must provide data for the data string.")

    coin_multiplier = int(1 / network.from_unit)

    tx.version = params["ttx_version"] # for upgradeability.
    tx.id = params["id"] # if type(params["id"]) == bytes else params["id"].encode("utf-8") # IDEM. TODO.

    if params["id"] == c.ID_PROPOSAL:

        tx.epochs = params["epoch_number"]
        tx.description = params["description"]

        if type(params["req_amount"]) in (Decimal, float):
            tx.amount = int(params["req_amount"] * coin_multiplier)
        else:
            tx.amount = params["req_amount"]
        if "first_ptx_txid" in params.keys() and params["first_ptx_txid"] is not None: # modified to prevent creation of empty fields.
            tx.txid = bytes.fromhex(params["first_ptx_txid"]) # EXPERIMENTAL: trying to save the space in modifications.


    else:
        tx.txid = bytes.fromhex(params["proposal_id"])

    if params["id"] == c.ID_LOCKING:
       tx.locktime = params["timelock"]
       tx.lockhash = address_to_hash(params["address"], params["lockhash_type"], network)
       tx.lockhash_type = params["lockhash_type"]

    elif params["id"] == c.ID_VOTING:
       tx.vote = params["vote"]

    check_size(tx, network)
    return tx.SerializeToString()


def serialize_deck_extended_data(network: tuple, deck: object=None, params: dict=None):

    if deck is not None:
        params = deck.__dict__
    elif params is None:
        raise ValueError("You must provide data for the data string.")

    d = DeckExtendedDataProto()
    d.id = params["at_type"]

    if d.id == c.ID_DT:
        d.epoch_len = params["epoch_length"]
        d.reward = params["epoch_reward"]
        d.min_vote = params["min_vote"]
        d.special_periods = params["sdp_periods"]
        d.voting_token_deckid = params["sdp_deckid"]
        d.extradata = params.get("extradata")
    elif d.id == c.ID_AT:
        d.multiplier = params["multiplier"]
        d.hash = address_to_hash(params["at_address"], params["addr_type"], network)
        d.hash_type = params["addr_type"]
        d.startblock = params["startblock"]
        d.endblock = params["endblock"]
        d.extradata = params.get("extradata")

    check_size(d, network)
    return d.SerializeToString()

def serialize_card_extended_data(network: tuple, card: object=None, id: bytes=None, txid: str=None):

    # NOTE: id scrapped. protocol re-checked, works now.
    if card is not None:
        txid = bytes.fromhex(card.donation_txid)

    c = CardExtendedDataProto()
    c.txid = bytes.fromhex(txid)

    check_size(c, network)
    return c.SerializeToString()

def check_size(obj, network):
    if obj.ByteSize() > network.op_return_max_bytes:
        raise OverSizeOPReturn('''Metainfo size exceeds maximum of {max} bytes supported by this network.'''
                                   .format(max=network.op_return_max_bytes))


def is_default_value(data):
    # print(data, type(data))
    if type(data) == bytes and data == b'':
        return True
    elif type(data) == int and data == "0":
        return True
    else: # bool type will not be reset to None.
        return False

def protobuf_to_dict(obj, clean=True):

    d = {}
    for field in obj.ListFields():

        if clean and is_default_value(field[1]):
            field_value = None
        else:
            field_value = field[1]

        d.update({ field[0].name : field_value })

    return d

class ProtobufCleaned:
    def __init__(protobuf_obj):
        pass



