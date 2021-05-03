"""all things PeerAssets protocol."""

# EXPERIMENTAL: All code changes related to "address tracking" assets are marked with ADDRESSTRACK

from enum import Enum
from operator import itemgetter
from typing import List, Optional, Generator, cast, Callable

from pypeerassets.kutil import Kutil
from pypeerassets.paproto_pb2 import DeckSpawn as deckspawnproto
from pypeerassets.paproto_pb2 import CardTransfer as cardtransferproto
from pypeerassets.exceptions import (
    InvalidCardIssue,
    OverSizeOPReturn,
    RecieverAmountMismatch,
)
from pypeerassets.card_parsers import parsers
from pypeerassets.networks import net_query

### ADDRESSTRACK ###
from pypeerassets.provider import Provider
from pypeerassets.at.transaction_formats import getfmt, DECK_SPAWN_AT_FORMAT, DECK_SPAWN_DT_FORMAT, CARD_ISSUE_DT_FORMAT, P2TH_MODIFIER
from pypeerassets.at.identify import is_at_deck, is_at_cardissue
from pypeerassets.at.dt_parser import dt_parser


class IssueMode(Enum):

    NONE = 0x00
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L19
    # No issuance allowed.

    CUSTOM = 0x01
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L20
    # Custom issue mode, verified by client aware of this.

    ONCE = 0x02
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L21
    # A single card_issue transaction allowed.

    MULTI = 0x04
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L22
    # Multiple card_issue transactions allowed.

    MONO = 0x08
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L23
    # All card transaction amounts are equal to 1.

    UNFLUSHABLE = 0x10
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L24
    # The UNFLUSHABLE issue mode invalidates any card transfer transaction except for the card issue transaction.
    # Meaning that only the issuing entity is able to change the balance of a specific address.
    # To correctly calculate the balance of a PeerAssets addres a client should only consider the card transfer
    # transactions originating from the deck owner.

    SUBSCRIPTION = 0x34  # SUBSCRIPTION (34 = 20 | 4 | 10)
    # https://github.com/PeerAssets/rfcs/blob/master/0001-peerassets-transaction-specification.proto#L26
    # The SUBSCRIPTION issue mode marks an address holding tokens as subscribed for a limited timeframe. This timeframe is
    # defined by the balance of the account and the time at which the first cards of this token are received.
    # To check validity of a subscription one should take the timestamp of the first received cards and add the address' balance to it in hours.

    SINGLET = 0x0a  # SINGLET is a combination of ONCE and MONO (2 | 8)
    #  Singlet deck, one MONO card issunce allowed


class Deck:

    def __init__(self, name: str,
                 number_of_decimals: int,
                 issue_mode: int,
                 network: str,
                 production: bool,
                 version: int,
                 asset_specific_data: bytes=None,
                 issuer: str="",
                 issue_time: int=None,
                 id: str=None,
                 tx_confirmations: int=None,
                 at_type=None,
                 multiplier: int=None,
                 epoch_length: int=None,
                 epoch_quantity: int=None,
                 min_vote: int=None,
                 sdp_periods: int=None,
                 sdp_deck: str=None) -> None:
        '''
        Initialize deck object, load from dictionary Deck(**dict) or initilize
        with kwargs Deck("deck", 3, "ONCE")'''

        self.version = version  # protocol version
        self.name = name  # deck name
        self.issue_mode = issue_mode  # deck issue mode
        self.number_of_decimals = number_of_decimals
        self.asset_specific_data = asset_specific_data  # optional metadata for the deck
        self.id = id
        self.issuer = issuer
        self.issue_time = issue_time
        self.tx_confirmations = tx_confirmations
        self.network = network
        self.production = production

        
        ### additional Deck attributes for AT/DT types:
        if self.asset_specific_data and self.issue_mode == IssueMode.CUSTOM.value:

            at_fmt = DECK_SPAWN_AT_FORMAT
            dt_fmt = DECK_SPAWN_DT_FORMAT
            data = self.asset_specific_data

            identifier = data[:2].decode()

            if identifier in ("AT", "DT"): # common to both formats
                self.at_type = identifier

            if identifier == "DT":
                if not epoch_length:
                    self.epoch_length = int.from_bytes(getfmt(data, dt_fmt, "dpl"), "big")
                if not epoch_quantity:
                    self.epoch_quantity = int.from_bytes(getfmt(data, dt_fmt, "tq"), "big")
                if not min_vote:
                    self.min_vote = int.from_bytes(getfmt(data, dt_fmt, "mnv"), "big")
                if not sdp_periods:
                    try:
                        self.sdp_periods = int.from_bytes(getfmt(data, dt_fmt, "sdq"), "big")
                        self.sdp_deck = getfmt(data, dt_fmt, "sdd").hex()
                    except IndexError:
                        pass # these 2 parameters are optional.

            elif identifier == "AT":
                self.multiplier = int.from_bytes(getfmt(data, at_fmt, "mlt"), "big")
                if not at_address:
                    self.at_address = getfmt(data, at_fmt, "adr").decode()

    @property ### MODIFIED VERSION TO OPTIMIZE SPEED ###
    def p2th_address(self) -> Optional[str]:
        '''P2TH address of this deck'''

        if self.id:
            try:
                if self._p2th_address:
                    return self._p2th_address
            except AttributeError:                
                self._p2th_address = Kutil(network=self.network,
                         privkey=bytearray.fromhex(self.id)).address

            return self._p2th_address
        else:
            return None


    @property ### MODIFIED VERSION TO OPTIMIZE SPEED ###
    def p2th_wif(self) -> Optional[str]:
        '''P2TH address of this deck'''

        if self.id:          
            try:
                if self._p2th_wif:
                    return self._p2th_wif
            except AttributeError:                
                self._p2th_wif = Kutil(network=self.network,
                         privkey=bytearray.fromhex(self.id)).wif

            return self._p2th_wif
        else:
            return None

    # EXPERIMENTAL: ids for the p2th addresses/keys for donation/proposal/signalling txs
    # They are stored in a dictionary, to avoid too much code repetition.
    def derived_id(self, tx_type) -> Optional[bytes]:
        if self.id:
            try:
                int_id = int(self.id, 16)
                derived_id = int_id - P2TH_MODIFIER[tx_type]
                return derived_id.to_bytes(32, "big")
            except KeyError:
                return None
            except OverflowError:
                # TODO: this is a workaround, should be done better!
                # It abuses that the OverflowError only can be raised because number becomes negative
                # So in theory a Proposal can be a high number, and signalling/donationtx a low one.
                max_id = int(b'\xff' * 32, 16)
                new_id = max_id - derived_id # TODO won't work as hex() gives strings!
                return new_id.to_bytes(32, "big")

        else:
            return None

    def derived_p2th_wif(self, tx_type) -> Optional[str]:
        if self.id:    
            try:

                if self.derived_p2th_wifs[tx_type] is not None:
                    return self.derived_p2th_wifs[tx_type]

            except AttributeError:
                self.derived_p2th_wifs = { tx_type : Kutil(network=self.network,
                         privkey=self.derived_id(tx_type)).wif }

            except KeyError:                
                self.derived_p2th_wifs.update({ tx_type : Kutil(network=self.network,
                         privkey=self.derived_id(tx_type)).wif })

            return self.derived_p2th_wifs[tx_type]
        else:
            return None

    def derived_p2th_address(self, tx_type) -> Optional[str]:

        if self.id:    

            try:
                if self.derived_p2th_addresses[tx_type] is not None:
                    return self.derived_p2th_addresses[tx_type]
            except AttributeError:
                self.derived_p2th_addresses = { tx_type : Kutil(network=self.network,
                         privkey=self.derived_id(tx_type)).address }
            except KeyError:                
                self.derived_p2th_addresses.update({ tx_type : Kutil(network=self.network,
                         privkey=self.derived_id(tx_type)).address })

            return self.derived_p2th_addresses[tx_type]
        else:
            return None

    @property
    def metainfo_to_protobuf(self) -> bytes:
        '''encode deck into protobuf'''

        deck = deckspawnproto()
        deck.version = self.version
        deck.name = self.name
        deck.number_of_decimals = self.number_of_decimals
        deck.issue_mode = self.issue_mode
        if self.asset_specific_data:
            if not isinstance(self.asset_specific_data, bytes):
                deck.asset_specific_data = self.asset_specific_data.encode()
            else:
                deck.asset_specific_data = self.asset_specific_data

        if deck.ByteSize() > net_query(self.network).op_return_max_bytes:
            raise OverSizeOPReturn('''
                        Metainfo size exceeds maximum of {max} bytes supported by this network.'''
                                   .format(max=net_query(self.network)
                                           .op_return_max_bytes))

        return deck.SerializeToString()

    @property
    def metainfo_to_dict(self) -> dict:
        '''encode deck into dictionary'''

        r = {
            "version": self.version,
            "name": self.name,
            "number_of_decimals": self.number_of_decimals,
            "issue_mode": self.issue_mode
        }

        if self.asset_specific_data:
            r.update({'asset_specific_data': self.asset_specific_data})

        return r

    def to_json(self) -> dict:
        '''export the Deck object to json-ready format'''

        d = self.__dict__
        d['p2th_wif'] = self.p2th_wif
        return d

    @classmethod
    def from_json(cls, json: dict):
        '''load the Deck object from json'''

        try:
            del json['p2th_wif']
        except KeyError:
            pass

        return cls(**json)        

    def __str__(self) -> str:

        r = []
        for key in self.__dict__:
            r.append("{key}='{value}'".format(key=key, value=self.__dict__[key]))

        return ', '.join(r)


class CardBundle:

    '''On the low level, cards come in bundles.
    A single transaction can contain dozens of cards.
    CardBundle is a object which is pre-coursor to CardTransfer'''

    def __init__(self,
                 deck: Deck,
                 sender: str,
                 txid: str,
                 blockhash: str,
                 blocknum: int,
                 blockseq: int,
                 timestamp: int,
                 tx_confirmations: int,
                 vouts: list=[],
                 ) -> None:

        self.deck = deck
        self.txid = txid
        self.sender = sender
        self.vouts = vouts

        if blockhash:
            self.blockhash = blockhash
            self.blockseq = blockseq
            self.timestamp = timestamp
            self.blocknum = blocknum
            self.tx_confirmations = tx_confirmations
        else:
            self.blockhash = ""
            self.blockseq = 0
            self.blocknum = 0
            self.timestamp = 0
            self.tx_confirmations = 0

    def to_json(self) -> dict:
        '''export the CardBundle object to json-ready format'''

        return self.__dict__


class CardTransfer:


    def __init__(self, deck: Deck, 
                 receiver: list=[],
                 amount: List[int]=[],
                 version: int=1,
                 blockhash: str=None,
                 txid: str=None,
                 sender: str=None,
                 asset_specific_data: bytes=None,
                 number_of_decimals: int=None,
                 blockseq: int=None,
                 cardseq: int=None,
                 blocknum: int=None,
                 timestamp: int=None,
                 tx_confirmations: int=None,
                 type: str=None,
                 move_txid: str=None,
                 donation_txid: str=None) -> None:

        '''CardTransfer object, used when parsing card_transfers from the blockchain
        or when sending out new card_transfer.
        It can be initialized by passing the **kwargs and it will do the parsing,
        or it can be initialized with passed arguments.
        * deck - instance of Deck object
        * receiver - list of receivers
        * amount - list of amounts to be sent, must be integer
        * version - protocol version, default 1
        * txid - transaction ID of CardTransfer
        * sender - transaction sender
        * blockhash - block ID where the tx was first included
        * blockseq - order in which tx was serialized into block
        * timestamp - unix timestamp of the block where it was first included
        * tx_confirmations - number of confirmations of the transaction
        * asset_specific_data - extra metadata
        * number_of_decimals - number of decimals for amount, inherited from Deck object
        : type: card type [CardIssue, CardTransfer, CardBurn]'''

        if not len(receiver) == len(amount):
            raise RecieverAmountMismatch

        self.version = version
        self.network = deck.network
        self.deck_id = deck.id
        self.deck_p2th = deck.p2th_address
        self.txid = txid
        self.sender = sender
        self.asset_specific_data = asset_specific_data
        if not number_of_decimals:
            self.number_of_decimals = deck.number_of_decimals
        else:
            self.number_of_decimals = number_of_decimals

        self.receiver = receiver
        self.amount = amount
        ### ADDRESSTRACK workaround ###
        self.deck_data = deck.asset_specific_data

        if blockhash:
            self.blockhash = blockhash
            self.blockseq = blockseq
            self.timestamp = timestamp
            self.blocknum = blocknum
            self.cardseq = cardseq
            self.tx_confirmations = tx_confirmations
        else:
            self.blockhash = ""
            self.blockseq = 0
            self.blocknum = 0
            self.timestamp = 0
            self.cardseq = 0
            self.tx_confirmations = 0

        ### AT ###
        # if deck contains correct addresstrack-specific metadata and the card references a txid,
        # the card type is CardIssue. Will be validated later by custom parser.
        # modified order because with AT tokens, deck issuer can be the receiver.
        # CardBurn is not implemented in AT, because the deck issuer should be
        # able to participate normally in the transfer process. Cards can however
        # be burnt sending them to unspendable addresses.

        if deck.issue_mode == IssueMode.CUSTOM.value:

            if is_at_deck(deck.asset_specific_data) == True:

                dt_fmt = CARD_ISSUE_DT_FORMAT
                if is_at_cardissue(self.asset_specific_data) == True:

                    self.type = "CardIssue"

                    if not donation_txid:
                        self.donation_txid = getfmt(self.asset_specific_data, dt_fmt, "dtx").hex()
                    else:
                        self.donation_txid = donation_txid
                  
                    # TODO: for now ID is hardcoded, should be changed
                    # MODIFIED: move_txid was removed.
                    #if deck.asset_specific_data[:2] == b'DT' and not move_txid:

                    #    if len(self.asset_specific_data) > 35:
                    #        self.move_txid = getfmt(self.asset_specific_data, dt_fmt, "mtx").hex()
                    #    else:
                    #        self.move_txid = None
                else:

                    self.type = "CardTransfer" # includes, for now, issuance attempts with completely invalid data

        elif self.sender == deck.issuer:
            # if deck issuer is issuing cards to the deck issuing address,
            # card is burn and issue at the same time - which is invalid!
            if deck.issuer in self.receiver:
                raise InvalidCardIssue
            else:
                # card was sent from deck issuer to any random address,
                # card type is CardIssue
                self.type = "CardIssue"

        # card was sent back to issuing address
        # card type is CardBurn
        elif self.receiver[0] == deck.issuer and not self.sender == deck.issuer:
            self.type = "CardBurn"

        # issuer is anyone else,
        # card type is CardTransfer
 
        else:
            self.type = "CardTransfer"

        if type:
            self.type = type

    @property
    def metainfo_to_protobuf(self) -> bytes:
        '''encode card_transfer info to protobuf'''

        card = cardtransferproto()
        card.version = self.version
        card.amount.extend(self.amount)
        card.number_of_decimals = self.number_of_decimals
        if self.asset_specific_data:
            if not isinstance(self.asset_specific_data, bytes):
                card.asset_specific_data = self.asset_specific_data.encode()
            else:
                card.asset_specific_data = self.asset_specific_data

        if card.ByteSize() > net_query(self.network).op_return_max_bytes:
            raise OverSizeOPReturn('''
                        Metainfo size exceeds maximum of {max} bytes supported by this network.'''
                                   .format(max=net_query(self.network)
                                           .op_return_max_bytes))

        return card.SerializeToString()

    @property
    def metainfo_to_dict(self) -> dict:
        '''encode card into dictionary'''

        r = {
            "version": self.version,
            "amount": self.amount,
            "number_of_decimals": self.number_of_decimals
        }

        if self.asset_specific_data:
            r.update({'asset_specific_data': self.asset_specific_data})

        return r

    def to_json(self) -> dict:
        '''export the CardTransfer object to json-ready format'''

        return self.__dict__

    @classmethod
    def from_json(cls, json: dict):
        '''load the Deck object from json'''

        return cls(**json)

    def __str__(self) -> str:

        r = []
        for key in self.__dict__:
            r.append("{key}='{value}'".format(key=key, value=self.to_json()[key]))

        return ', '.join(r)

    def deck_data(self): ### ADDRESSTRACK: needed for parser. Look for a more elegant solution. ###
        return deck.asset_specific_data


def validate_card_issue_modes(issue_mode: int, cards: list, provider: Provider=None, deck: Deck=None) -> list:
    """validate cards against deck_issue modes"""
    ### ADDRESSTRACK modification: including provider variable for custom parser and including deck ###

    if len(cards) == 0: ### MODIF: if there are no cards, cards[0] cannot work ###
        return []

    supported_mask = 63  # sum of all issue_mode values

    if not bool(issue_mode & supported_mask):
        return []  # return empty list

    for i in [1 << x for x in range(len(IssueMode))]:
        if bool(i & issue_mode):

            try:
                parser_fn = cast(
                    Callable[[list], Optional[list]],
                    parsers[IssueMode(i).name]
                )
            except ValueError:
                continue

            if is_at_deck(cards[0].deck_data): ### ADDRESSTRACK modification ###
                parsed_cards = parser_fn(cards, dt_parser, provider, deck) # was at_parser before
            else:
                parsed_cards = parser_fn(cards)
 
            if not parsed_cards:
                return []
            cards = parsed_cards

    return cards


class DeckState:

    def __init__(self, cards: Generator) -> None:

        self.cards = cards
        self.total = 0
        self.burned = 0
        self.balances = cast(dict, {})
        self.processed_issues = set()
        self.processed_transfers = set()
        self.processed_burns = set()

        self.calc_state()
        self.checksum = not bool(self.total - sum(self.balances.values()))

    def _process(self, card: dict, ctype: str) -> bool:

        sender = card["sender"]
        receiver = card["receiver"][0]
        amount = card["amount"][0]

        if ctype != 'CardIssue':
            balance_check = sender in self.balances and self.balances[sender] >= amount

            if balance_check:
                self.balances[sender] -= amount

                if 'CardBurn' not in ctype:
                    self._append_balance(amount, receiver)

                return True

            return False

        if 'CardIssue' in ctype:
            self._append_balance(amount, receiver)
            return True

        return False

    def _append_balance(self, amount: int, receiver: str) -> None:

            try:
                self.balances[receiver] += amount
            except KeyError:
                self.balances[receiver] = amount

    def _sort_cards(self, cards: Generator) -> list:
        '''sort cards by blocknum and blockseq'''

        return sorted([card.__dict__ for card in cards],
                            key=itemgetter('blocknum', 'blockseq', 'cardseq'))

    def calc_state(self) -> None:

        for card in self._sort_cards(self.cards):

            # txid + blockseq + cardseq, as unique ID
            cid = str(card["txid"] + str(card["blockseq"]) + str(card["cardseq"]))
            ctype = card["type"]
            amount = card["amount"][0]

            if ctype == 'CardIssue' and cid not in self.processed_issues:
                validate = self._process(card, ctype)
                self.total += amount * validate  # This will set amount to 0 if validate is False
                self.processed_issues |= {cid}

            if ctype == 'CardTransfer' and cid not in self.processed_transfers:
                self._process(card, ctype)
                self.processed_transfers |= {cid}

            if ctype == 'CardBurn' and cid not in self.processed_burns:
                validate = self._process(card, ctype)

                self.total -= amount * validate
                self.burned += amount * validate
                self.processed_burns |= {cid}
