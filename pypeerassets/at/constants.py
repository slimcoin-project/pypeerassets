# Constants contains some general constants of the AT and DT extensions.

from enum import Enum

# Deck version used for pypeerassets.at and dt

DECK_VERSION = 1

# Round division.
# Minimal round unit (e.g. one signalling/locking/donation round) is a fraction of one epoch divided by this number.

DT_ROUND_DIVISION = 28

# TrackedTransaction Constants. All TrackedTransactions must follow this scheme of outputs.

P2TH_OUTPUT=0 # output which goes to P2TH address
DATASTR_OUTPUT=1 # output with data string (OP_RETURN)
DONATION_OUTPUT=2 # output with donation/signalling amount
RESERVED_OUTPUT=3 # output for a reservation for other rounds.

# Enum classes

class DeckTypeID(Enum):

    NONE = 0
    DT = 1
    AT = 2

class TtxID(Enum):

    NONE = 0
    PROPOSAL = 1
    VOTING = 2
    SIGNALLING = 3
    LOCKING = 4
    DONATION = 5

# P2TH modifier

P2TH_MODIFIER = { "proposal" : TtxID.PROPOSAL.value,
                  "voting" : TtxID.VOTING.value,
                  "signalling" : TtxID.SIGNALLING.value,
                  "locking" : TtxID.LOCKING.value,
                  "donation" : TtxID.DONATION.value }

# Short deck identifiers

ID_DT = DeckTypeID.DT.value
ID_AT = DeckTypeID.AT.value

# Abbreviations for deck identifiers

DECK_TYPES = [[None], ["dt", "pod", "dpod"], ["at", "pob", "dico"]]

# TTX identifiers

ID_NONE = TtxID.NONE.value
ID_PROPOSAL = TtxID.PROPOSAL.value
ID_VOTING = TtxID.VOTING.value
ID_SIGNALLING = TtxID.SIGNALLING.value
ID_LOCKING = TtxID.LOCKING.value
ID_DONATION = TtxID.DONATION.value

# legacy compatibility

TTXIDDICT = { "proposal" : TtxID.PROPOSAL.value,
              "voting" : TtxID.VOTING.value,
              "signalling" : TtxID.SIGNALLING.value,
              "locking" : TtxID.LOCKING.value,
              "donation" : TtxID.DONATION.value }

def get_id(tx_type: str):
    return TTXIDDICT[tx_type]

def get_deck_type(deck_type: str):
    for index, decktype_values in enumerate(DECK_TYPES):
        if deck_type in decktype_values:
            return index


