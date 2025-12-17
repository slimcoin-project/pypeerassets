import pytest
import random
import itertools
from pypeerassets import Kutil
from pypeerassets.protocol import (CardTransfer, Deck, IssueMode,
                                   validate_card_issue_modes, DeckState)
from pypeerassets.exceptions import OverSizeOPReturn, InvalidCardIssue

# note: CardLocks are of type CardTransfer.

# @pytest.mark.parametrize("locktime", [0, 1, 10, 1000])
def test_deck_state_with_locktime():
    '''test DeckState calculations with 2024/25 locktime additions'''

    deck = Deck(
        name="my_test_deck",
        number_of_decimals=0,
        issue_mode=4,  # MULTI
        network="tslm",
        production=True,
        version=1,
        issuer='mueRM5EauG5KetKeLsXe1y23HdGXAXEkJa'
        )

    receiver_roster = ['miDmEStqYmyWXU3pm9w34gKSUkhGsCEsST',
                       'mov1Tt2LdGju9un8uba3RubVZvVw3s7znV',
                       'ms3CXTfLdAX21NwnkGH8WFH2TYQjd9VwZg',
                       'ms2wRgjFL2MPpJU1ZpWi5sLMxDnqCuaTB6']
    lock_address_roster = ['mmVXfumjbbra6j8H26wRQEZA4u9dEHQNwN',
                           'myrDqrtPcqJzPKzsKp5UxFokFfk3KW3sir',
                           'n2CWRSTUnhLnY2eqnwrG95VGKq3D6ke22d',
                           'mw1QmGMsY3omwmwtGQfDqBQX9AThUV8yEP']
    lockhash_roster = [bytes.fromhex(h) for h in
                       ['418bc8cbe0ffd20cc7cf0caaa98f6e58d90e1d59',
                       'c9172582e208aeae79bdcb903489c7f9fb886434',
                       'e2dd8e86606f82ad0f48d9c139e2c351b582cf8d',
                       'a9eba1085a9a765b477a8bac038f136abd3d5d4e']] # correspond to lock addresses 1-4

    amounts = [10, 20, 30, 40]

    # block 1: all cardissues

    card_issues = [CardTransfer(deck=deck,
                                receiver=[r],
                                amount=[a],
                                sender=deck.issuer,
                                blockseq=0,
                                blocknum=1,
                                blockhash='d9ec32b461d80b6a549a09f5ddd550f6e2fa9021f8efe4fd7413be6c471c0b56',
                                txid='fe8f88c2a3a700a664f9547cb9c48466f900553d0a6bdb504ad52340ef00c9a0',
                                cardseq=amounts.index(a)
                                ) for r, a in zip(receiver_roster, amounts)]

    transfers = []  # list of card transfers

    # block 2
    # 1. R0 (owns 10 cards) locks 10 cards to L0
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[0],
                                  receiver=[receiver_roster[0]],
                                  amount=[10],
                                  blockhash='c5a03576178843eb5a1f1e6b878678f2c7d47b6f561fe06059e0518645b8e50e',
                                  blocknum=2,
                                  blockseq=1,
                                  cardseq=0,
                                  txid='08c886a43ce9f95a5673bc95374259b0f9eca9de1e5fb9bb7aa7826834820133',
                                  type='CardTransfer',
                                  locktime=10,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[0]
                                  ))

    # 2. R1 (owns 20 cards) locks 10 cards to L1
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[1],
                                  receiver=[receiver_roster[1]],
                                  amount=[10],
                                  blockhash='c5a03576178843eb5a1f1e6b878678f2c7d47b6f561fe06059e0518645b8e50e',
                                  blocknum=2,
                                  blockseq=2,
                                  cardseq=0,
                                  txid='08c886a43ce9f95a5673bc95374259b0f9eca9de1e5fb9bb7aa7826834820134', # fake txid
                                  type='CardTransfer',
                                  locktime=10,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[1]
                                  ))
    # 3. R2 (owns 30 cards) locks 31 cards to L3 -> must fail
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[2],
                                  receiver=[receiver_roster[2]],
                                  amount=[31],
                                  blockhash='c5a03576178843eb5a1f1e6b878678f2c7d47b6f561fe06059e0518645b8e50e',
                                  blocknum=2,
                                  blockseq=3,
                                  cardseq=0,
                                  txid='08c886a43ce9f95a5673bc95374259b0f9eca9de1e5fb9bb7aa7826834820135', # fake txid
                                  type='CardTransfer',
                                  locktime=10,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[2]
                                  ))

    # 4. R3 (owns 40 cards) locks 40 cards to L3, with different receiver (R2). R3 doesn't own any cards anymore.
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[3],
                                  receiver=[receiver_roster[2]],
                                  amount=[40],
                                  blockhash='c5a03576178843eb5a1f1e6b878678f2c7d47b6f561fe06059e0518645b8e50e',
                                  blocknum=2,
                                  blockseq=4,
                                  cardseq=0,
                                  txid='08c886a43ce9f95a5673bc95374259b0f9eca9de1e5fb9bb7aa7826834820136', # fake txid
                                  type='CardTransfer',
                                  locktime=10,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[3]
                                  ))
    # block 3
    # 5. R2 (owns 30 cards) locks 30 cards to L2 -> must go through even if the cards were tried to be locked, because #3 failed
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[2],
                                  receiver=[receiver_roster[2]],
                                  amount=[30],
                                  blockhash='d6cecad875b05e9b34cb05680de0bee4f5d69ba83df23a6b6a14d1090dc992e3',
                                  blocknum=3,
                                  blockseq=0,
                                  cardseq=0,
                                  txid='08c886a43ce9f95a5673bc95374259b0f9eca9de1e5fb9bb7aa7826834820137', # fake txid
                                  type='CardTransfer',
                                  locktime=10,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[2]
                                  ))

    # 6. R3 locks 10 cards to L3 -> must fail, cards are not owned as #4 went to different receiver.
    # Note: this one is actually not checking the lock but the receiver change
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[3],
                                  receiver=[lock_address_roster[3]],
                                  amount=[10],
                                  blockhash='d6cecad875b05e9b34cb05680de0bee4f5d69ba83df23a6b6a14d1090dc992e3',
                                  blocknum=3,
                                  blockseq=1,
                                  cardseq=0,
                                  txid='08c886a43ce9f95a5673bc95374259b0f9eca9de1e5fb9bb7aa7826834820138', # fake txid
                                  type='CardTransfer',
                                  locktime=10,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[3]
                                  ))


    # 7. attempt to burn locked coins: R0 has all 10 coins locked. -> must fail
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[0],
                                  receiver=[deck.issuer],  # burn
                                  amount=[5],
                                  blockseq=2,
                                  blockhash='d6cecad875b05e9b34cb05680de0bee4f5d69ba83df23a6b6a14d1090dc992e3',
                                  cardseq=0,
                                  blocknum=3,
                                  txid='b27161ba476d29c2255d097aaa4e236752b9891a46d1fdb88f5225ee677b976e',
                                  type='CardBurn'
                                  ))
    # block 5
    # 8. R1 tries to move remaining 10 coins (10 locked, 10 available) to L3 -> must go through
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[1],
                                  receiver=[lock_address_roster[3]],
                                  amount=[10],
                                  blockseq=0,
                                  blocknum=5,
                                  blockhash='d638dc2d60623d16cb6b39fc165a6e7514a28c426b02db32058b87fada1cabdb',
                                  cardseq=0,
                                  txid='ebe36158ca3f364910f8a1c0f9b1b2696bed4522f84551bdb42ffd57360ce232',
                                  type='CardTransfer'
                                  ))

    # 9. R2 tries to move 20 coins (all are locked) to R3 -> must fail
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[2],
                                  receiver=[receiver_roster[3]],
                                  amount=[20],
                                  blockseq=1,
                                  blocknum=5,
                                  blockhash='d638dc2d60623d16cb6b39fc165a6e7514a28c426b02db32058b87fada1cabdb',
                                  txid='ebe36158ca3f364910f8a1c0f9b1b2696bed4522f84551bdb42ffd57360ce233', # fake txid
                                  type='CardTransfer',
                                  cardseq=0
                                  ))

    # block 6
    # 10. L0 tries to move 10 cards -> not possible, as a CardLock does not mean the lock address owns the card.
    transfers.append(CardTransfer(deck=deck,
                                  sender=lock_address_roster[0],
                                  receiver=[receiver_roster[1]],
                                  amount=[10],
                                  blockseq=0,
                                  blocknum=6,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7a',
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0fe',
                                  type='CardTransfer',
                                  cardseq=0
                                  ))

    # 11. R0 moves the 10 locked cards to L0 (the lock address it locked the cards to).
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[0],
                                  receiver=[lock_address_roster[0]],
                                  amount=[10],
                                  blockseq=1,
                                  blocknum=6,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7a',
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0fd', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0
                                  ))
    # 12. R1 moves 5 locked cards (less than the 10 locked cards) to L1 (the lock address it had sent them).
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[1],
                                  receiver=[lock_address_roster[1]],
                                  amount=[5],
                                  blockseq=2,
                                  blocknum=6,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7a',
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0fc', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0
                                  ))
    # block 7
    # 13. L0 moves the 10 received cards to L1 -> goes through, L0 now has no cards anymore.
    transfers.append(CardTransfer(deck=deck,
                                  sender=lock_address_roster[0],
                                  receiver=[lock_address_roster[1]],
                                  amount=[10],
                                  blockseq=0,
                                  blocknum=7,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7b', # fake blockhash
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0fb', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0
                                  ))
    # 14. L1 tries to move 10 cards to L2. It owns now 15 (5 from tx 12 and 10 from tx 13, but tx 12 has zero confirmations.)
    # should go through because blockseq is taken into account. L1 has now 5 cards.
    transfers.append(CardTransfer(deck=deck,
                                  sender=lock_address_roster[1],
                                  receiver=[lock_address_roster[2]],
                                  amount=[10],
                                  blockseq=1,
                                  blocknum=7,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7b', # fake blockhash
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0fa', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0
                                  ))
    # block 20 (all locks are free again)
    # 15. R2 tries to move 50 cards to L3. His 30 cards are unlocked and he got 40 from R3 in #4, so it should be valid.
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[2],
                                  receiver=[lock_address_roster[3]],
                                  amount=[50],
                                  blockseq=0,
                                  blocknum=20,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7c', # fake blockhash
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0f9', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0
                                  ))
    # 16. R3 tries to move 10 cards -> should fail as he locked them with different receiver, so they haven't "returned to his property".
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[3],
                                  receiver=[lock_address_roster[3]],
                                  amount=[10],
                                  blockseq=1,
                                  blocknum=20,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7c', # fake blockhash
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0f8', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0
                                  ))

    # 17. R1 moves 5 coins to L1 and locks them to L3 for 100 blocks.
    transfers.append(CardTransfer(deck=deck,
                                  sender=receiver_roster[1],
                                  receiver=[lock_address_roster[1]],
                                  amount=[5],
                                  blockseq=2,
                                  blocknum=20,
                                  blockhash='2896066f76f0c0f609ee0e92d195d0eb48891b91f90fa4c9a51381e9f9510b7c', # fake blockhash
                                  txid='764afbfe6b3cecd3be8161fef363a08b8b14e7c631b4b7fbbc8edbc1475ab0f7', # fake txid, downwards
                                  type='CardTransfer',
                                  cardseq=0,
                                  locktime=100,
                                  lockhash_type=2,
                                  lockhash=lockhash_roster[3]
                                  ))


    state = DeckState(card_issues + transfers)

    assert len(state.cards) == 21 # 4 issues + 16 transfers + 1 burn
    assert len(state.valid_cards) == 15 # 6 should result in invalid CardTransfers
    assert len(list(state.processed_burns)) == 1
    assert len(list(state.valid_burns())) == 0
    assert len(list(state.processed_issues)) == 4
    assert len(list(state.processed_transfers)) == 16
    assert state.checksum

    assert state.balances[receiver_roster[0]] == 0 # all were transfered to lock address 0
    assert state.balances[receiver_roster[1]] == 0 # 10 were locked, 5 of them transferred to lock address, 10 + 5 were transferred to other addresses
    assert state.balances[receiver_roster[2]] == 20 # locked 30 but never transferred them, later received 40 and transferred 50
    assert state.balances[receiver_roster[3]] == 0 # locked 40 but never transferred them, went to another receiver.
    assert state.balances[lock_address_roster[0]] == 0 # received 10 but transferred them to L1
    assert state.balances[lock_address_roster[1]] == 10 # received 10 from L0, 5 + 5 from R1, and moved 10 to L2. 5 of these tokens are locked.
    assert state.balances[lock_address_roster[2]] == 10 # received 10 from L1
    assert state.balances[lock_address_roster[3]] == 60 # received 10 from R1 and 50 from R2

    assert receiver_roster[1] not in state.locks
    assert len(state.locks[lock_address_roster[1]]) == 1
    assert state.locks[lock_address_roster[1]][0]["locktime"] == 100
