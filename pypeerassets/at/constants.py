# Constants contains some general constants of the AT and DT extensions.

from enum import Enum

# Deck version used for pypeerassets.at and dt

DECK_VERSION = 1

# TrackedTransaction Constants. All TrackedTransactions must follow this scheme of outputs.

P2TH_OUTPUT=0 # output which goes to P2TH address
DATASTR_OUTPUT=1 # output with data string (OP_RETURN)
DONATION_OUTPUT=2 # output with donation/signalling amount
RESERVED_OUTPUT=3 # output for a reservation for other rounds.

# Deck identifiers

DT_ID = b'DT' # TODO: later to be changed to enums
AT_ID = b'AT'

# TTX identifiers

ID_PROPOSAL = b'DP'
ID_SIGNALLING = b'DS'
ID_LOCKING = b'DL'
ID_DONATION = b'DD'
ID_VOTING = b'DV'

# P2TH modifier
# TODO: the modifier could be tied to the TtxID. This would change position 2+ (but anyway al P2TH will be change).

P2TH_MODIFIER = { "proposal" : 1, "voting" : 2, "donation" : 3, "signalling" : 4, "locking" : 5 }

# enum classes:

class DeckID(Enum):

    DT = 1
    AT = 2

class TtxID(Enum):

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

