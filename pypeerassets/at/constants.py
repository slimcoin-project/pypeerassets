# Constants contains some general constants of the AT and DT extensions.

from enum import Enum

# Deck version used for pypeerassets.at and dt

DECK_VERSION = 1

# TrackedTransaction Constants. All TrackedTransactions must follow this scheme of outputs.

P2TH_OUTPUT=0 # output which goes to P2TH address
DATASTR_OUTPUT=1 # output with data string (OP_RETURN)
DONATION_OUTPUT=2 # output with donation/signalling amount
RESERVED_OUTPUT=3 # output for a reservation for other rounds.

# P2TH modifier

# P2TH_MODIFIER = { "proposal" : 1, "voting" : 2, "donation" : 3, "signalling" : 4, "locking" : 5 }
P2TH_MODIFIER = { "proposal" : 1, "voting" : 2, "signalling" : 3, "locking" : 4, "donation" : 5 }
# TODO this is a first workaround to stabilize protocol asap, should later be solved more elegant.

# enum classes:

class DeckTypeID(Enum):

    DT = 1
    AT = 2

class TtxID(Enum):

    NONE = 0
    PROPOSAL = 1
    VOTING = 2
    SIGNALLING = 3
    LOCKING = 4
    DONATION = 5

#class P2THModifier(Enum):
#    PROPOSAL = 1
#    VOTING = 2
#    DONATION = 3
#    SIGNALLING = 4
#    LOCKING = 5

# Deck identifiers

DT_ID = DeckTypeID.DT.value
AT_ID = DeckTypeID.AT.value

# old
#DT_ID = b'DT'
#AT_ID = b'AT'

# TTX identifiers

ID_NONE = TtxID.NONE.value
ID_PROPOSAL = TtxID.PROPOSAL.value
ID_VOTING = TtxID.VOTING.value
ID_SIGNALLING = TtxID.SIGNALLING.value
ID_LOCKING = TtxID.LOCKING.value
ID_DONATION = TtxID.DONATION.value

# old:
#ID_PROPOSAL = b'DP'
#ID_SIGNALLING = b'DS'
#ID_LOCKING = b'DL'
#ID_DONATION = b'DD'
#ID_VOTING = b'DV'

