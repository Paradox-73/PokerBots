#!/bin/bash
# cand20.zip under numpy 1.26 / 1.23 (Python 3.11) in the organisers' two-leg engine (kit2); prints both bots' lines
H=~/synergy_pokerbots; KIT=$H/kit2
for X in 126 123; do
  PY=$H/np$X/bin/python; T=$H/npc20_$X; rm -rf $T; mkdir -p $T/bot; cd $T
  $PY -c "import zipfile; zipfile.ZipFile('$H/cand20.zip').extractall('bot')"; chmod -R a-w bot
  for spec in "1 random example_bots/random_bot.py 1" "2 starter bot.py 4"; do set -- $spec
    echo "== np$X stage $1 vs $2 seed $4"
    taskset -c 12 $PY -I $KIT/engine.py bot/bot.py $KIT/$3 --stage $1 --seed $4 --log-dir $T/logs_$4 --python $PY 2> $T/err_$4.txt | grep -E '^ +[AB] |Result|orfeit'
    echo "engine stderr lines: $(wc -l < $T/err_$4.txt); bot stderr lines: $(cat $T/logs_$4/A_leg*_stderr.txt | wc -l)"
  done
done
echo NPDONE
