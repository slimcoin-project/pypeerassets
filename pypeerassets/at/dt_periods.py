from pypeerassets.at.dt_states import ProposalState

def get_period_dict(ps: ProposalState) -> dict:

    # first periods are added manually
    # A: before the distribution start & B: first dist period
    submission_epoch_start = ps.first_ptx.epoch * ps.deck.epoch_length
    periods = {("A", 0) : [0, submission_epoch_start], ("A", 1) : [submission_epoch_start, ps.dist_start - 1],
               ("B", 0) : ps.security_periods[0], ("B", 1) : ps.voting_periods[0]}

    for rd in range(4):
        periods.update({("B", rd * 10) : ps.rounds[rd][0], ("B", rd * 10 + 1) : ps.rounds[rd][1]})

    # C: Working period: from first block after round 3 until block before security period 1 & D: second dist period
    periods.update({("C", 0) : [ ps.rounds[3][1][1] + 1, ps.security_periods[1][0] - 1 ],
                    ("D", 0) : ps.security_periods[1], ("D", 1) : ps.voting_periods[1], ("D", 2) : ps.release_period})

    for rd in range(4):
        periods.update({("D", rd * 10) : ps.rounds[rd + 4][0], ("D", rd * 10 + 1) : ps.rounds[rd + 4][1]})
    dist_end = (ps.end_epoch + 1) * ps.deck.epoch_length - 1

    # D50 & E: After the distribution
    periods.update({("D", 50) : [ps.rounds[7][1][1] + 1, dist_end], ("E", 0) : [dist_end + 1, None]})

    return periods


def period_query(period_dict: dict, block: int) -> tuple:
    for key, value in period_dict.items():

        [start, end] = value # value is list

        if end is None:
            end = block # this will make the check fail if it's not in E 0, because E 0 is the last period of all
        if start <= block <= end:
            # returns a tuple, otherwise lookup is more complicated (tuple: period[0], dict: period.keys()[0])
            return (key, value)

def get_startendvalues(period: tuple, ps: ProposalState) -> list:
    return get_period_dict(ps)[period]

def humanreadable_to_periodcode(period_str: str, period_index: int) -> tuple:
    """The humanreadable format is for example 'voting, 1' or 'signalling, 2' """

    epoch_codes = ("B", "D") # B is "phase 1", D is "phase 2"
    pre_dist_periods = ("security", "voting", "release")
    dist_periods = ("signalling", "donation")
    dist_phase = period_index // 4 # gives 0 or 1, only needed for signalling/donation

    if period_index > 4:
        period_index -= 4 # round 4-8 become round 1-5 of phase 2
    if period_str in pre_dist_periods:
        # TODO: this does not rule out "release", 0 which would be invalid, do we need to catch this?
        return (epoch_codes[period_index], pre_dist_periods.index(period_str))
    else:
        return (epoch_codes[dist_phase], period_index * 10 + dist_periods.index(period_str))

    
