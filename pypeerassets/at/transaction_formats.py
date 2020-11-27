#!/usr/bin/env python3

"""Basic formats of donation/proposal/signalling transactions and other constants.

Format is a a dictionary with tuples: 

- the first is the position of the first byte of the item in the OP_RETURN bytestring 
- the second one is the byte length of the item. If it is variable, then this value has to be 0.

Note: OP_RETURN has 100 bytes maximum, so no large numbers of items can be stored.
"""

ID_LEN = 2 # TODO: this maybe has to be changed to 1. For the testing purposes it can stay at 2.
TX_LEN = 32 # length of all items comprising TXIDs
EPOCH_LEN = 2 # up to 65535 epochs
SLOTAC_LEN = 2 # slot allocation, up to 65535 blocks (~65 days).
AMOUNT_LEN = 6 # up to 256 million SLM
MLT_LEN = 2 # multiplier of up to 65535 # only AT
DP_LEN = 3 # distribution length of up to ~16 million blocks
MNV_LEN = 1 # minimum vote (0/256 to 256/256)
TQ_LEN = 2 # token quantity per round, up to 65535
SDP_LEN = 1 # sdp periods, up to 256

# some general constants (originally in parser file, but we need them elsewhere.)

# This is the minimum amount of blocks after a new epoch start before a new voting or slot allocation period can start, to prevent any edge effects.
# TODO: This would better be realized as a variable depending from epoch length. Minimum can stay at 1.
DEFAULT_SECURITY_PERIOD = 1
# roughly equivalent to 7 days; 1 day has between ~960 and ~1100 blocks
DEFAULT_VOTING_PERIOD = 1 # test for PPC # was 7500 

# slot allocation phases/rounds
PHASE1_ROUNDS = (0, 1, 2, 3)
PHASE2_ROUNDS = (4, 5, 6, 7, 8)

# Proposal transaction
# TODO: Maybe previous_txid is not necessary, it could be enough to use the epoch where the vote took place.
# This is because both need to share the same address, so votes can be easily taken from there.
# It would mean one calculation less in the initialization of proposal_txes.

# Addition: We may need an ID for the non-Peerassets TXs to identify the proposal transactions clearly.
# In theory they're identified also by P2TH so it's not totally necessary.

PROPOSAL_FORMAT = { "id" : (0, ID_LEN), # identification of proposal txes, 2 bytes
                    "dck" : (ID_LEN, TX_LEN), # deck, 32 bytes
                    "eps" : (ID_LEN + TX_LEN, EPOCH_LEN), # epochs the "worker" needs, 2 bytes
                    "sla" : (ID_LEN + TX_LEN + EPOCH_LEN, SLOTAC_LEN), # slot allocation period, 2 bytes
                    "amt" : (ID_LEN + TX_LEN + EPOCH_LEN + SLOTAC_LEN, AMOUNT_LEN), # amount, 6 bytes
                    "ptx" : (TX_LEN + EPOCH_LEN + SLOTAC_LEN + AMOUNT_LEN, TX_LEN) # previous proposal (optional), 32 bytes
                  }


# Donation transaction
# needed data: deck, proposal transaction
# MODIFIED: Deck deleted in the following three formats. It is derived from the associated Proposal.

DONATION_FORMAT = { "id" : (0, ID_LEN), # identification of donation txes
                    "prp" : (ID_LEN, TX_LEN), # proposal txid
                  }

# Signalling transaction
# needed data: deck, proposal transaction
# Deck may not be necessary! Can be derived probably from the P2TH id.

SIGNALLING_FORMAT = { "id" : (0, ID_LEN),
                    "prp" : (ID_LEN, TX_LEN), 
                    }

VOTING_FORMAT = { "id" : (0, ID_LEN),
                    "prp" : (ID_LEN, TX_LEN), 
                    "vot" : (ID_LEN + TX_LEN, 1)
                    }

# Coin Issues
# Deck not necessary, as it's already in the CardTransfer structure.
# Card Issue data for AT: 2 bytes as AT identifier, TXID (32 bytes), vout (rest)
# Card Issue data for DT: 2 bytes as DT identifier, TXID (32 bytes), vout (rest)
# MODIFIED: optional argument "mtx" (moving transaction)
# CHECK: It could be possible to only require MTX OR DTX if it's possible to differentiate them
# probably yes: because MTX has always be checked for DTX.

CARD_ISSUE_AT_FORMAT = { "id" : (0, ID_LEN),
                  "dtx" : (ID_LEN, TX_LEN),
                  "out" : (ID_LEN + TX_LEN, 1)
                }

# TODO: check if "out" is needed, as per convention donation amounts are always in vout "2".
CARD_ISSUE_DT_FORMAT = { "id" : (0, ID_LEN),
                  "dtx" : (ID_LEN, TX_LEN),
                  "out" : (ID_LEN + TX_LEN, 1),
                  "mtx" : (ID_LEN + TX_LEN + 1, TX_LEN)
                }

# Deck Spawn
# Deck data for AT: 2 bytes as AT identifier, Multiplier (2 bytes, up to 65535), Address (rest).
# Deck data for DT: 2 bytes as DT identifier, length of distribution period (3 bytes, up to ~16 million), tokens per distribution period (2 bytes, up to 65535), Proposer vote threshold (1 byte), Special Distribution periods (1 byte), TXID of deck of SDP token (32 bytes) => 42 bytes

DECK_SPAWN_AT_FORMAT = { "id" : (0, ID_LEN), # identifier of AT decks
                  "mlt" : (ID_LEN, MLT_LEN), # multiplier
                  "adr" : (ID_LEN + MLT_LEN, 0) # donation address
                 }

DECK_SPAWN_DT_FORMAT = { "id" : (0, ID_LEN), # identifier of DT decks
                  "dpl" : (ID_LEN, DP_LEN), # distribution period length in blocks
                  "tq" : (ID_LEN + DP_LEN, TQ_LEN), # token quantity
                  "mnv" : (ID_LEN + DP_LEN + TQ_LEN, MNV_LEN), # minimum vote
                  "sdq" : (ID_LEN + DP_LEN + TQ_LEN + MNV_LEN, SDP_LEN),
                  "sdd" : (ID_LEN + DP_LEN + TQ_LEN + MNV_LEN + SDP_LEN, TX_LEN)
                 }

DECK_SPAWN_DT_FORMAT_OLD = { "id" : (0, ID_LEN), # identifier of DT decks
                  "mlt" : (ID_LEN, MLT_LEN), # multiplier
                  "dpl" : (ID_LEN + MLT_LEN, DP_LEN), # distribution period length in blocks
                  "tq" : (ID_LEN + MLT_LEN + DP_LEN, TQ_LEN), # token quantity
                  "mnv" : (ID_LEN + MLT_LEN + DP_LEN + TQ_LEN, MNV_LEN), # minimum vote
                  "sdq" : (ID_LEN + MLT_LEN + DP_LEN + TQ_LEN + MNV_LEN, SDP_LEN),
                  "sdd" : (ID_LEN + MLT_LEN + DP_LEN + TQ_LEN + MNV_LEN + SDP_LEN, TX_LEN)
                 }

######## P2TH ########
""" PRELIMINARY convention for now:
- proposal: deck p2th -1
- signalling: deck p2th +1
- donation: deck p2th +2
"""
P2TH_MODIFIER = { "donation" : 1, "signalling" : 2, "proposal" : 3 }

def getfmt(strvar, fmt, key):
  # this function returns the part of a string or bytes variable defined in these formats.
  begin = fmt[key][0]
  if fmt[key][1] == 0: # variable length 
      return strvar[begin:]
  else:
      end = fmt[key][0] + fmt[key][1]
      return strvar[begin:end]

