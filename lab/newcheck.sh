#!/bin/bash
# Engine checks under the new two-leg rules (organisers' engine kit2/engine.py). usage: newcheck.sh ZIP TAG
# Six tester matches with peak memory, start-up, unknown messages, 998 hands, slowed core -> NEWCHECKDONE
H=~/synergy_pokerbots; Z=$1; PY=$H/.venv/bin/python; KIT=$H/kit2; T=$H/newcheck_$2
chmod -R u+w $T 2>/dev/null; rm -rf $T; mkdir -p $T/bot; cd $T
$PY -c "import zipfile; zipfile.ZipFile('$Z').extractall('bot')"; chmod -R a-w bot
md5sum $Z bot/bot.py; $PY -V; $PY -c 'import numpy; print("numpy", numpy.__version__)'
cp -r $KIT/example_bots $KIT/bot.py .
run() {  # LABEL CORE ENGINE OPP STAGE SEED [extra]
  echo "== $1"
  taskset -c $2 /usr/bin/time -v $PY -I $3 bot/bot.py $4 --stage $5 --seed $6 ${7:+$7} --log-dir $T/l$6 --python $PY 2> $T/time_$6.txt | grep -E ' A | B |Result|forfeit'
  grep -E "Maximum resident" $T/time_$6.txt
  echo "   our stderr lines per leg: $(cat $T/l$6/A_leg1_stderr.txt | wc -l) $(cat $T/l$6/A_leg2_stderr.txt | wc -l)"
}
run "stage 1 vs random" ${C1:-13} $KIT/engine.py example_bots/random_bot.py 1 1
run "stage 1 vs starter" ${C1:-13} $KIT/engine.py bot.py 1 2
run "stage 2 vs random" ${C1:-13} $KIT/engine.py example_bots/random_bot.py 2 3
run "stage 2 vs starter" ${C1:-13} $KIT/engine.py bot.py 2 4
run "stage 2 vs starter" ${C1:-13} $KIT/engine.py bot.py 2 5
run "stage 1 vs random" ${C1:-13} $KIT/engine.py example_bots/random_bot.py 1 6
echo "== start-up to exit, 5 runs (limit 5 s)"
for i in 1 2 3 4 5; do /usr/bin/time -f "%e s" $PY -I bot/bot.py <<< '{"type":"match_end","reason":"complete"}'; done
$PY - $KIT/engine.py <<'PYEOF'
import sys
s = open(sys.argv[1]).read()
a = r'data = json.dumps(msg, separators=(",", ":")) + "\n"'
b = r'data = json.dumps({"type": "zz_new", "v": 9}) + "\n" + json.dumps(dict(msg, zz_field={"k": [1]}), separators=(",", ":")) + "\n"'
assert s.count(a) == 1
open("engine_fuzz.py", "w").write(s.replace(a, b))
PYEOF
run "unknown message types and fields, stage 1 vs random" ${C2:-12} engine_fuzz.py example_bots/random_bot.py 1 7
run "unknown message types and fields, stage 2 vs starter" ${C2:-12} engine_fuzz.py bot.py 2 8
run "998-hand stage 2 match vs starter" ${C2:-12} $KIT/engine.py bot.py 2 9 "--hands 998"
taskset -c ${C3:-10} yes > /dev/null & Y1=$!; taskset -c ${C3:-10} yes > /dev/null & Y2=$!
run "stage 2 vs mid-strength rival, core shared with two CPU hogs" ${C3:-10} $KIT/engine.py $H/frozen/rival_c/bot.py 2 10
run "stage 1 vs mid-strength rival, same slowed core" ${C3:-10} $KIT/engine.py $H/frozen/rival_c/bot.py 1 11
kill $Y1 $Y2
echo NEWCHECKDONE
