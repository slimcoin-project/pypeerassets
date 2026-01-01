# NOTE: The purpose of the DummyDeck/DummyCard classes is to circunvent the Deck/Card initialization
# enabling to separate test units.
# TODO: evaluate if this is not counter-productive,
# as the vanilla unittests use the original Deck/CardTransfer objects.

class TestObj(object):
   """Minimal test object to fill with keyword arguments. Mostly used for TrackedTransactions."""
   __test__ = False
   def __init__(self, **kwargs):
       for k, v in kwargs.items():
           setattr(self, k, v)

class DummyCard:

    def __init__(self, **kwargs):

        self.txid = kwargs["txid"]
        self.amount = [kwargs["amount"]]
        self.number_of_decimals = kwargs["number_of_decimals"]
        self.sender = kwargs["sender"]
        self.blocknum = kwargs["blocknum"]
        self.blockseq = kwargs["blockseq"]
        self.cardseq = kwargs["cardseq"]
        self.type = kwargs["ctype"]

        if "receiver" in kwargs:
            self.receiver = kwargs["receiver"]
        else:
            self.receiver = ["DUMMY"] # in some tests we don't need to check an address here.


class DummyATCard(DummyCard):

    def __init__(self, **kwargs):

        super().__init__(**kwargs)
        self.donation_txid = kwargs["donation_txid"]

class DummyDeck:

    def __init__(self, **kwargs):

        self.id = kwargs["deckid"]
        self.number_of_decimals = kwargs["number_of_decimals"]

class DummyATDeck(DummyDeck):


    def __init__(self, **kwargs):

        super().__init__(**kwargs)
        self.at_address = kwargs["at_address"]
        self.multiplier = kwargs["multiplier"]
        self.startblock = kwargs["startblock"]
        self.endblock = kwargs["endblock"]


class DummyProvider:

    def __init__(self, tx_dummies, block_dummies):
        self.tx_dummies = tx_dummies
        self.block_dummies = block_dummies

    def getrawtransaction(self, txid, json_mode):
        assert json_mode == 1
        for tx in self.tx_dummies:
            if tx["txid"] == txid:
                return tx

    def getblock(self, blockhash):
        for b in self.block_dummies:
            if b["hash"] == blockhash:
                return b


