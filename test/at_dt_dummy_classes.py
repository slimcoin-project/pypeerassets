class DummyATCard:

    def __init__(self, **kwargs):

        self.txid = kwargs["txid"]
        self.amount = [kwargs["amount"]]
        self.donation_txid = kwargs["donation_txid"]
        self.number_of_decimals = kwargs["number_of_decimals"]
        self.sender = kwargs["sender"]
        self.blocknum = kwargs["blocknum"]
        self.blockseq = kwargs["blockseq"]
        self.cardseq = kwargs["cardseq"]
        self.type = kwargs["ctype"]
        self.receiver = ["DUMMY"] # we don't need to check an address here.

class DummyATDeck:

    def __init__(self, **kwargs):

        self.id = kwargs["deckid"]
        self.at_address = kwargs["at_address"]
        self.multiplier = kwargs["multiplier"]
        self.startblock = kwargs["startblock"]
        self.endblock = kwargs["endblock"]

