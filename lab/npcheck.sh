#!/bin/bash
# cand11.zip under numpy 1.26 / 1.23 (Python 3.11) in the organisers' engine; same seeds as org_test2 -> NPDONE in npcheck.out
H=~/synergy_pokerbots; KIT=$H/repo/docs/starter_kit
for X in 126 123; do
  PY=$H/np$X/bin/python; T=$H/npt_$X; rm -rf $T; mkdir -p $T/bot; cd $T
  $PY -c "import zipfile; zipfile.ZipFile('$H/cand11.zip').extractall('bot')"; chmod -R a-w bot
  for spec in "1 random example_bots/random_bot.py 1" "2 starter bot.py 4"; do set -- $spec
    echo "== np$X stage $1 vs $2 seed $4"
    taskset -c 12 $PY -I $KIT/engine.py bot/bot.py $KIT/$3 --stage $1 --seed $4 --log-dir $T/logs_$4 2> $T/err_$4.txt | tail -4
    echo "engine stderr lines: $(wc -l < $T/err_$4.txt)"; grep -ril 'traceback\|error' $T/logs_$4 | head -3
  done
done
echo NPDONE
