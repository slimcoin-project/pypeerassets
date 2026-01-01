"""all things PeerAssets protocol."""

# EXPERIMENTAL: All code changes related to "address tracking" assets are marked with ADDRESSTRACK
# EXPERIMENTAL: This is the version with locktime and lockhash, suitable for DEXes.
# TODO: AT burns are still shown as CardTransfers.

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
import pypeerassets.at.extension_protocol as ep
### LOCK ###
from pypeerassets.hash_encoding import hash_to_address
from pypeerassets.at.constants import P2TH_MODIFIER, ID_DT, ID_AT
from pypeerassets.provider import Provider

# P2TH_MODIFIER = { "proposal" : 1, "voting" : 2, "donation" : 3, "signalling" : 4, "locking" : 5 }

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
                 epoch_reward: int=None,
                 min_vote: int=None,
                 sdp_periods: int=None,
                 sdp_deck: str=None,
                 at_address: str=None,
                 addr_type: str=None,
                 startblock: int=None,
                 endblock: int=None,
                 extradata: bytes=None) -> None:
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

        ### ADDRESSTRACK: outsource custom attributes of extensions
        # TODO: for beta 2: the custom attributes should go into a single dict-style attribute of the deck,
        # so the ugly self argument isn't necessary.
        # a class "ExtensionAttributes" or similar would be best.

        if self.issue_mode == IssueMode.CUSTOM.value:

            ep.initialize_custom_deck_attributes(self,
                                                 network,
                                                 at_type=at_type,
                                                 epoch_length=epoch_length,
                                                 epoch_reward=epoch_reward,
                                                 min_vote=min_vote,
                                                 sdp_periods=sdp_periods,
                                                 sdp_deck=sdp_deck,
                                                 multiplier=multiplier,
                                                 at_address=at_address,
                                                 addr_type=addr_type,
                                                 startblock=startblock,
                                                 endblock=endblock,
                                                 extradata=extradata)


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

    ### DT: ids for the p2th addresses/keys for donation/proposal/signalling txs
    ### They are stored in a dictionary, to avoid too much code repetition.
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
                 locktime: int=None,
                 lockhash: str=None,
                 lockhash_type: str=None,
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
        self.type = None

        # Modifications for Locktime features
        self.locktime = locktime
        if lockhash and lockhash_type and locktime:
            self.lockhash = lockhash
            self.lockhash_type = lockhash_type

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

        # Modifications for AT and DT features.
        # Defines the type of the CardTransfer and some other attributes.
        # if deck contains correct addresstrack-specific metadata and the card references a txid,
        # the card type is CardIssue. Will be validated later by custom parser.
        # MODIF: CardBurn also works for AT and DT tokens now.
        # Rationale: There is no reason to encourage re-use of addresses here.

        if deck.issue_mode == IssueMode.CUSTOM.value:
            ep.initialize_custom_card_attributes(self, deck, donation_txid=donation_txid)

        if self.type is not None:
             # if issue mode is already set by extension, preserve it.
            pass
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

        if type: # allows overriding, but not of the InvalidCardIssue
            self.type = type

        self.cid = "{}{}{}".format(str(txid), str(blockseq), str(cardseq))


    @property
    def metainfo_to_protobuf(self) -> bytes:
        '''encode card_transfer info to protobuf'''

        card = cardtransferproto()
        card.version = self.version
        card.amount.extend(self.amount)
        card.number_of_decimals = self.number_of_decimals
        if self.locktime: ### LOCK addition (we don't use a version here, because of the deck version problem)
            card.locktime = self.locktime
            if self.lockhash:
                 card.lockhash = self.lockhash
                 card.lockhash_type = self.lockhash_type
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

        # Modifications for Locktime features
        if self.locktime:
            r.update({'locktime': self.locktime})
        if self.lockhash:
            r.update({'lockhash' : self.lockhash})
            r.update({'lockhash_type' : self.lockhash_type})

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


def validate_card_issue_modes(issue_mode: int, cards: list, provider: Provider=None, deck: Deck=None) -> list:
    """validate cards against deck_issue modes"""
    # AT/DT modifications: including provider variable for custom parser and including deck ###

    if len(cards) == 0: # AT/DT bugfix
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

            try: # AT/DT. The AttributeError is thrown when no Protobuf data is found.

                if cards[0].at_type == ID_DT:  # modification for extended parsers
                    import pypeerassets.at.dt_parser as dtp
                    parsed_cards = parser_fn(cards, dtp.dt_parser, provider, deck)

                elif cards[0].at_type == ID_AT:
                    import pypeerassets.at.at_parser as atp
                    parsed_cards = parser_fn(cards, atp.at_parser, provider, deck)

            except AttributeError:
                parsed_cards = parser_fn(cards)

            if not parsed_cards:
                return []
            cards = parsed_cards

    return cards


class DeckState:
    # Added attribute valid_cards to be able to process only the valid (non-bogus) cards.
    # Locktime: self.lock is dict of senders, with dicts including locktime and amount.
    # cleanup_height cleans locks remaining after the last card.

    def __init__(self, cards: Generator, cleanup_height: int=None, debug: bool=False) -> None:

        self.cards = cards
        self.total = 0
        self.burned = 0
        self.balances = cast(dict, {})
        self.processed_issues = set()
        self.processed_transfers = set()
        self.processed_burns = set()

        # addresstrack and lock modifications
        self.valid_cards = cast(list, [])
        self.debug = debug
        self.locks = cast(dict, {})
        self.cleanup_height = cleanup_height

        self.calc_state()
        self.checksum = not bool(self.total - sum(self.balances.values()))

    def _process(self, card: dict, ctype: str) -> bool:

        sender = card["sender"]
        receiver = card["receiver"][0]
        amount = card["amount"][0]

        if ctype != 'CardIssue':

            ### LOCKS: adding current_locks here prevents locked cards to be transfered.
            ### They will be simply invalid, the rest would also not be transfered.
            locked_amount = self._check_locks(sender, receiver, amount, card["blocknum"], card["network"])
            # DEBUG information
            if self.debug:
                if card["locktime"]: # this detects a CardLock
                    print("CardLock:     blocknum {} sender {} receiver {} amount {} locktime {} lockhash {} lockhash_type {}".format(card["blocknum"], sender, receiver, amount, card["locktime"], card.get("lockhash"), card.get("lockhash_type")))
                else:
                    print("CardTransfer: blocknum {} sender {} receiver {} amount {}".format(card["blocknum"], sender, receiver, amount))
                if len(self.locks):
                    print("locked amount of sender {} before card: {}".format(sender, locked_amount))
                    print("locked senders:", [s for s in self.locks])
            balance_check = sender in self.balances and (self.balances[sender] - locked_amount) >= amount

            if balance_check:

                self.balances[sender] -= amount

                if 'CardBurn' not in ctype:
                    self._append_balance(amount, receiver)

                    if card["locktime"]:
                        # we add the lock to the receiver's address.
                        self._add_lock(receiver, amount, card["locktime"], card.get("lockhash"), card.get("lockhash_type"))

                return True

            if self.debug:
                print("Not valid: balance: {}, locked amount: {}, card amount: {}".format(self.balances.get(sender), locked_amount, amount))
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

            if self.cleanup_height:
                if card["blocknum"] > self.cleanup_height:
                    break

            # txid + blockseq + cardseq, as unique ID
            # cid = str(card["txid"] + str(card["blockseq"]) + str(card["cardseq"]))
            ctype = card["type"]
            amount = card["amount"][0]

            if ctype == 'CardIssue' and card["cid"] not in self.processed_issues:
                validate = self._process(card, ctype)
                self.total += amount * validate  # This will set amount to 0 if validate is False
                self.processed_issues |= {card["cid"]}
                if validate:
                    self.valid_cards.append(card_from_dict(card))

            if ctype == 'CardTransfer' and card["cid"] not in self.processed_transfers:
                validate = self._process(card, ctype)
                if validate:
                    self.valid_cards.append(card_from_dict(card))
                    # subtract the amount of the card from locks.
                    if card["sender"] in self.locks:
                        self._unlock_amount(card["sender"], card["receiver"][0], amount, card["network"])

                self.processed_transfers |= {card["cid"]}

            if ctype == 'CardBurn' and card["cid"] not in self.processed_burns:
                validate = self._process(card, ctype)

                self.total -= amount * validate
                self.burned += amount * validate
                self.processed_burns |= {card["cid"]}
                if validate: ### changed from here
                    self.valid_cards.append(card_from_dict(card))

        ### LOCKS: cleanup if height is provided
        if self.cleanup_height:
            self._cleanup_locks()

    def valid_burns(self):
        valid_card_set = set([c.cid for c in self.valid_cards])
        return valid_card_set & self.processed_burns

    def _cleanup_locks(self):
        if self.debug:
            print("Cleaning up locks up to blockheight:", self.cleanup_height)
        for address in list(self.locks):
            if self.debug:
               print("Locks on address", address, self.locks[address], len(self.locks[address]))
            # we go from the last index to the first, so if the list changes, indexes aren't modified.
            for index in range(len(self.locks[address]) - 1, -1, -1):
                lock = self.locks[address][index]
                # print(index, lock["locktime"])
                if lock["locktime"] < self.cleanup_height:
                    if self.debug:
                        print("Cleaning up lock:", lock)
                    self._modify_lock(address, lock["amount"], index)
                elif self.debug:
                    print("Lock preserved:", lock)

    def _check_locks(self, cardsender: str, receiver: str, amount: int, blocknum: int, network: str) -> int:
        if self.debug:
            print("================================")
            if len(self.locks):
                print("Current locks at block {}: {}".format(blocknum, self.locks))
        # we unset locks at each CardTransfer
        # Unlocking after a transfer done to lock_address is only done after validating.
        locked_amount = 0
        original_locks = self.locks.copy()
        for locksender in original_locks.keys():
            for index in range(len(self.locks[locksender]) - 1, -1, -1):
                # reversed loop, see rationale in _cleanup_locks.
                # we check all locks for expiration, not only those of the card sender,
                # so expired locks do not clutter up the lock dict.
                try:
                    lock = self.locks[locksender][index]
                except KeyError:
                    break # can happen after the last lock was removed
                if lock["locktime"] < blocknum:
                    # when the lock expires, the complete lock is reverted.
                    # Thus we unlock the whole amount of the lock (lock["amount"]).
                    self._modify_lock(locksender, lock["amount"], index)

                elif cardsender == locksender:

                    # address locks (type 1 to 6) - other types are still not implemented.
                    if lock["lockhash_type"] in range(1, 6):
                        # MODIF: added lock_address to lock dict, to prevent hash_to_address
                        # being calculated more than once.
                        if "lock_address" not in lock.keys():
                            addr = calc_lock_address(lock, network)
                            self.locks[locksender][index].update({"lock_address" : addr })
                        else:
                            addr = lock["lock_address"]

                        if addr != receiver:
                            if self.debug:
                                print("Active address/hash timelock: +", lock["amount"], "lock address", addr)
                            locked_amount += self.locks[locksender][index]["amount"]
                    elif lock["lockhash_type"] == None:
                        if self.debug:
                            print("Active simple timelock: +", lock["amount"])
                        locked_amount += self.locks[locksender][index]["amount"]

                    # old variant with specific lock_address:
                    #if lock["address"] != receiver:
                    #    # if lock_address is not defined, or not equal to receiver, then locked amount is increased.
                    #    print("Active lock: +", lock["amount"], "lock address", lock["address"])
                    #    locked_amount += self.locks[locksender][index]["amount"]

        return locked_amount

    # NOTE: this only covers address locks for now!
    def _unlock_amount(self, sender: str, rec_address: str, amount: int, network: str) -> None:
        # checks if the card was transfered to an address in self.locks.
        # If yes, it unlocks an amount transferred to rec_address. Various locks can be affected.
        unlocked_amount = amount
        # sort: highest index is with the lowest locktime,
        # this means early locks will be cleared first
        self.locks[sender].sort(key=lambda x: x['locktime'], reverse=True)
        for index in range(len(self.locks[sender]) - 1, -1, -1):
            lock = self.locks[sender][index]

            # no lockhash or wrong type: tokens cannot be unlocked before locktime expires.
            if lock.get("lockhash") is None or lock["lockhash_type"] not in range(1, 6):
                if self.debug:
                    print("Cannot unlock lock of type {} or without lockhash.".format(lock["lockhash_type"]))
                continue

            if "lock_address" not in lock.keys():
                addr = calc_lock_address(lock, network)
                self.locks[sender][index].update({"lock_address" : addr })
            else:
                addr = lock["lock_address"]

            if addr != rec_address:
                continue

            if unlocked_amount > lock["amount"]:
                # if the unlocked amount is bigger than the amount of the particular lock,
                # then the loop continues through the locks with the same lock address.
                self._modify_lock(sender, lock["amount"], index)
                unlocked_amount -= lock["amount"]
                if self.debug:
                    print("Unlocking entire lock amount", lock["amount"], "for receiving address", rec_address)
                    if unlocked_amount > 0:
                        print("Still to unlock:", unlocked_amount)
            else:
                self._modify_lock(sender, unlocked_amount, index)
                if self.debug:
                    print("Unlocking amount", unlocked_amount, "for receiving address", rec_address)
                break

    def _add_lock(self, address: str, amount: int, locktime: int, lockhash: str=None, lockhash_type: int=None) -> None:
        lock_dict = {"locktime": locktime, "amount" : amount, "lockhash" : lockhash, "lockhash_type" : lockhash_type}
        if address not in self.locks:
           self.locks.update({address : [lock_dict] })
        else:
           self.locks[address].append(lock_dict)

    def _modify_lock(self, address: str, unlocked_amount: int, index: int) -> None:
        # modifies (i.e. lowers amount) or deletes a lock.
        lock = self.locks[address][index]
        if lock["amount"] > unlocked_amount:
            self.locks[address][index]["amount"] -= unlocked_amount
            if self.debug:
                print("Modified lock: lowered by", unlocked_amount)
        else:
            # Delete locks with amount zero.
            if len(self.locks[address]) > 1:
                del self.locks[address][index]
                if self.debug:
                    print("Modified lock: deleted lock of", unlocked_amount)
            else:
                del self.locks[address]
                if self.debug:
                    print("Modified lock: deleted sender of lock list, unlocked", unlocked_amount)

def calc_lock_address(lock: dict, network: str) -> None:
    return hash_to_address(lock["lockhash"], lock["lockhash_type"], net_query(network))


def card_from_dict(d): ### WORKAROUND. TODO: Look for a more elegant solution!
    c = CardTransfer.__new__(CardTransfer)
    for (key, value) in d.items():
        setattr(c, key, value)
    return c



