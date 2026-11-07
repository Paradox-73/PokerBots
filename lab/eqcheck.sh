#!/bin/bash
# Same-moves check: VERSION_A and VERSION_B run with fixed random seeds and a fixed run-out count
# (the only clock-dependent input), each against a fixed-seed copy of A. Identical match logs = same play.
# The harness is first run twice on A to show it is deterministic. usage: eqcheck.sh A B -> EQDONE
H=~/synergy_pokerbots; PY=$H/.venv/bin/python; KIT=$H/kit2; T=$H/eq_$1_$2
rm -rf $T; mkdir -p $T; cd $T
for v in $1 $2; do
cat > det_$v.py <<EOF
import importlib.util, random, sys
import numpy as np
spec = importlib.util.spec_from_file_location("botmod", "$H/vers/$v/bot.py")
m = importlib.util.module_from_spec(spec)
sys.modules["botmod"] = m
spec.loader.exec_module(m)
_rng = np.random.default_rng
np.random.default_rng = lambda seed=None, *a, **k: _rng(12345 if seed is None else seed)
random.seed(7)
np.random.seed(7)
m.Bot.runouts = lambda self: 64
_load = m.load_solver
def seeded_solver():
    s = _load()
    s.rng = random.Random(99)  # the solver maps opponent bet sizes with random draws
    return s
m.load_solver = seeded_solver
m.main()
EOF
done
cp det_$1.py opp.py
play() {  # LABEL BOT STAGE SEED
  taskset -c ${CORE:-10} $PY -I $KIT/engine.py $2 opp.py --stage $3 --seed $4 --log-dir $T/$1_s$3_$4 --python $PY | grep -E ' A |Result|orfeit' | sed 's/time used.*//'
  grep -v -i -e 'time' -e '^Logs:' $T/$1_s$3_$4/match.log | md5sum
}
A=$1; B=$2
for spec in "1 1" "1 2" "2 3"; do set -- $spec
  echo "== stage $1 seed $2"
  echo "-- $A run 1"; play ${A}_r1 det_$A.py $1 $2
  echo "-- $A run 2"; play ${A}_r2 det_$A.py $1 $2
  echo "-- $B"; play $B det_$B.py $1 $2
done
echo EQDONE
