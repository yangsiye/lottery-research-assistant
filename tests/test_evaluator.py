from lottery_assistant.evaluator import evaluate_single, evaluate_multiple

def test_dlt_single_tier():
    r=evaluate_single('dlt',[1,2,3,4,5],[1,2],[1,2,3,4,9],[1,2],pool_ge_800m=True)
    assert r['main_hits']==4 and r['bonus_hits']==2 and r['tier']=='三等奖' and r['fixed_prize']==6666

def test_dlt_7_3_cost_and_wins():
    r=evaluate_multiple('dlt',[1,2,3,4,5,6,7],[1,2,3],[1,2,3,4,5],[1,2],additional=True,pool_ge_800m=False)
    assert r['bet_count']==63 and r['cost']==189
    assert r['winning_tiers']['一等奖']==1
    assert r['contains_floating_prize'] is True

def test_ssq_multiple():
    r=evaluate_multiple('ssq',[1,2,3,4,5,6,7],[1,2],[1,2,3,4,5,6],[1])
    assert r['bet_count']==14 and r['cost']==28
    assert r['winning_tiers']['一等奖']==1
