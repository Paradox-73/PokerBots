#!/bin/bash
# Near-jam variants of the f15 attacker (all-in minus 2 chips on turn/river with >= 62% equity), each one change:
#   l1 / l6 / l15  leave 1 / 6 / 15 chips    flop  also on the flop    pre  on every street    bluff  no equity floor
# Each is smoke-tested against cand29 (stderr line counts, result). SMOKEDONE in njv_smoke.log
H=~/synergy_pokerbots; PY=$H/.venv/bin/python; R=$H/rivals2; cd $H
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
mk() { mkdir -p $R/nj_$1; sed "$2" $R/f15/bot.py > $R/nj_$1/bot.py; echo "nj_$1 changed lines: $(diff $R/f15/bot.py $R/nj_$1/bot.py | grep -c '^>')" >> njv_smoke.log; }
mk l1 's/^NJ_LEAVE = 2$/NJ_LEAVE = 1/'
mk l6 's/^NJ_LEAVE = 2$/NJ_LEAVE = 6/'
mk l15 's/^NJ_LEAVE = 2$/NJ_LEAVE = 15/'
mk flop 's/if STREET\[req\["street"\]\] < 2 or/if STREET[req["street"]] < 1 or/'
mk pre 's/if STREET\[req\["street"\]\] < 2 or/if STREET[req["street"]] < 0 or/'
mk bluff 's/^NJ_MIN_EQ = 0.62 /NJ_MIN_EQ = 0.0 /'
for v in l1 l6 l15 flop pre bluff; do
  (d=/tmp/njs_$v; rm -rf $d; taskset -c 0-13 nice -n 5 $PY -I kit2/engine.py $R/nj_$v/bot.py $H/vers/cand29/bot.py --stage 1 --seed 997 --log-dir $d --python $PY > $d.out 2>&1
   echo "nj_$v smoke: stderr A $(cat $d/A_leg*_stderr.txt | grep -c .) B $(cat $d/B_leg*_stderr.txt | grep -c .); $(grep ' A ' $d.out | head -1)" >> njv_smoke.log) &
done
wait
echo SMOKEDONE >> njv_smoke.log
