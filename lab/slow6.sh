#!/bin/bash
# Shipped zip on a core shared with 5 CPU hogs (about 1/6 speed) vs the fast random bot, so only our
# bot's speed matters: does it stay inside the bank and the per-reply limit? -> SLOW6DONE in slow6.txt
H=~/synergy_pokerbots; PY=$H/.venv/bin/python; KIT=$H/kit2; T=$H/slow6; C=${CORE:-13}
chmod -R u+w $T 2>/dev/null; rm -rf $T; mkdir -p $T/bot; cd $T
$PY -c "import zipfile; zipfile.ZipFile('$1').extractall('bot')"; chmod -R a-w bot; md5sum $1
for i in 1 2 3 4 5; do taskset -c $C yes > /dev/null & done
for spec in "1 21" "2 22"; do set -- $spec
  echo "== stage $1 seed $2, 1/6-speed core"
  /usr/bin/time -f "wall %e s" taskset -c $C $PY -I $KIT/engine.py bot/bot.py $KIT/example_bots/random_bot.py --stage $1 --seed $2 --log-dir $T/l$2 --python $PY 2>&1 | grep -E ' A | B |Result|orfeit|wall'
  echo "   our stderr lines: $(cat $T/l$2/A_leg*_stderr.txt | wc -l)"
done
pkill -P $$ yes
echo SLOW6DONE
