import pytest
import pypeerassets.at.dt_states as ds


from decimal import Decimal
from .at_dt_dummy_classes import TestObj

COIN=100000000
CENT=1000000

pytest.skip("Has errors, postponed to later betas.", allow_module_level=True)

st = ds.DonationState()
# slots

@pytest.mark.parametrize("dist_round", range(6))
def test_get_slot(dist_round):
    # This test only checks if the slot calculations are correct, not the validity of the transactions.
    # we only need an unique string as TXID.
    # Later other tests could check:
    # - LockingTxes being higher or lower than the corresponding SignallingTxes.
    stx = TestObj(amount=1*COIN, txid=str(dist_round) + "aa")
    txid_begin = ["0", "0", "1", "2", "0", "4", "0", "0"]
    rtx = TestObj(reserved_amount=2*COIN, txid=txid_begin[dist_round] + "fa")
    req_amount = 50*COIN
    stxes = [None]*8
    dtxes = [None]*8
    eslots = [None]*8
    signalled_amounts, locked_amounts, donated_amounts, reserved_amounts = [], [], [], []

    stxes[0] = [TestObj(amount=1*COIN, txid="0aa"), TestObj(amount=2*COIN, txid="0ab")]
    stxes[1] = [TestObj(amount=1*COIN, txid="1aa"), TestObj(amount=3*COIN, txid="1ab")] # P
    stxes[2] = [TestObj(amount=1*COIN, txid="2aa"), TestObj(amount=150*CENT, txid="2ab")] # P
    stxes[3] = [TestObj(amount=1*COIN, txid="3aa"), TestObj(amount=250*CENT, txid="3ab")]
    stxes[4] = [TestObj(amount=1*COIN, txid="4aa"), TestObj(amount=3*COIN, txid="4ab")] # P
    stxes[5] = [TestObj(amount=1*COIN, txid="5aa"), TestObj(amount=4*COIN, txid="5ab")] # P
    stxes[6] = [TestObj(amount=1*COIN, txid="6aa"), TestObj(amount=1*COIN, txid="6ab")]
    stxes[7] = [TestObj(amount=1*COIN, txid="7aa"), TestObj(amount=2*COIN, txid="7ab")]

    # Locking/Donation transactions (We don't add the amount, we take it from SignallingTxes).
    dtxes[0] = [TestObj(reserved_amount=2*COIN, txid="0fa"), TestObj(reserved_amount=120*CENT, txid="0fb")] #P4, P1
    dtxes[1] = [TestObj(reserved_amount=2*COIN, txid="1fa"), TestObj(reserved_amount=380*CENT, txid="1fb")] #P4, P2
    dtxes[2] = [TestObj(reserved_amount=2*COIN, txid="2fa"), TestObj(reserved_amount=2*COIN, txid="2fb")] # P4
    dtxes[3] = [TestObj(reserved_amount=2*COIN, txid="3fa"), TestObj(reserved_amount=5*COIN, txid="3fb")] # P4
    dtxes[4] = [TestObj(reserved_amount=2*COIN, txid="4fa"), TestObj(reserved_amount=4*COIN, txid="4fb")] # P5
    dtxes[5] = [TestObj(reserved_amount=2*COIN, txid="5fa"), TestObj(reserved_amount=430*CENT, txid="5fb")]
    dtxes[6] = [TestObj(reserved_amount=2*COIN, txid="6fa"), TestObj(reserved_amount=870*CENT, txid="6fb")]
    dtxes[7] = [TestObj(reserved_amount=2*COIN, txid="7fa"), TestObj(reserved_amount=3*COIN, txid="7fb")]

    # For Reserve Transactions, only consider DonationTxes from the following rounds.
    # rtxes = [[], dtxes[0], dtxes[1], [], [d for r in dtxes[:4] for d in r], dtxes[4], [], []]

    # we assume that everybody donates everything they signal and lock. Thus effective locking slots (elslots) are equal to donation slots (edslots), and signalled/locking/donated amounts are the same.

    for rd in range(8):
        donated_amounts = locked_amounts = signalled_amounts.append(sum([s.amount for s in stxes[rd]]))
        #locked_amounts.append(sum([s.amount for s in stxes[rd]]))
        #donated_amounts.append(sum([s.amount for s in stxes[rd]]))
        reserved_amounts.append(sum([r.reserved_amount for r in dtxes[rd]]))


    # rd1 = (1 + 2) = 3/50
    eslots[0] = 3*COIN
    # rd2 = (2 + 1.2 + 1 + 3) = 7.2 / 47
    eslots[1] = 720*CENT
    # rd3 = (2 + 3.8 + 1 + 1.5) = 8.3 / 39.8
    eslots[2] = 830*CENT
    # rd4 = (1 + 2.5) = 3.5 / 31.5
    eslots[3] = 350*CENT
    # rd5a = (2 + 1.2 + 2 + 3.8 + 2 + 2 + 2 + 5) = 20 / 28
    # rd5b =  (1 + 3) = 4 / 8
    eslots[4] = 24 * COIN # (20 + 4)*COIN
    # rd6a = (2 + 4) = 6 / 4
    # rd6b = (1 + 4) = 5 / 0
    eslots[5] = 4 # (6 + 5)*COIN
    # rd7 = (1 + 1) = 2 / 0
    eslots[6] = 0 # 2*COIN
    # rd8 = (1 + 2) = 3 / 0
    eslots[7] = 0 # 3*COIN
    elslots = eslots

    stx_slot = st.get_slot(tx=stx,
                       dist_round=dist_round,
                       signalling_txes=stxes,
                       locking_txes=dtxes,
                       donation_txes=dtxes,
                       signalled_amounts=signalled_amounts,
                       locked_amounts=locked_amounts,
                       donated_amounts=donated_amounts,
                       reserved_amounts=reserved_amounts,
                       first_req_amount=req_amount,
                       final_req_amount=req_amount,
                       effective_slots=eslots,
                       effective_locking_slots=elslots)

    rtx_slot = st.get_slot(tx=rtx,
                       dist_round=dist_round,
                       signalling_txes=stxes,
                       locking_txes=dtxes,
                       donation_txes=dtxes,
                       signalled_amounts=signalled_amounts,
                       locked_amounts=locked_amounts,
                       donated_amounts=donated_amounts,
                       reserved_amounts=reserved_amounts,
                       first_req_amount=req_amount,
                       final_req_amount=req_amount,
                       effective_slots=eslots,
                       effective_locking_slots=elslots)

    # values for req_amount = 50
    expected_slots_stx = [100000000,100000000,100000000,100000000,100000000,0,0,0]
    expected_slots_rtx = [0,200000000,200000000,0,200000000,133333333,0,0]
    # explanation: in this example, in round 5 the slots are filled, and there is only space for "reserve txes"
    # but not for the complete signalled amount but for 2/3 of them. Thus the slot in round 5
    # is 133333333 for the RTX but 0 for the STX (which has a lower priority).
    assert stx_slot == expected_slots_stx[dist_round]
    assert rtx_slot == expected_slots_rtx[dist_round]
