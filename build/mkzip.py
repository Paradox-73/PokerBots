"""Build an upload zip: bot.py only, at the top level, fixed 1980-01-01 time stamp.
usage: mkzip.py BOT_PY OUT_ZIP"""
import hashlib, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
data = open(src, "rb").read()
info = zipfile.ZipInfo("bot.py", date_time=(1980, 1, 1, 0, 0, 0))
info.compress_type = zipfile.ZIP_DEFLATED
info.create_system = 3
info.external_attr = 0o600 << 16
with zipfile.ZipFile(out, "w") as z:
    z.writestr(info, data)
z = zipfile.ZipFile(out)
assert z.namelist() == ["bot.py"] and z.read("bot.py") == data
assert len(open(out, "rb").read()) < 5 * 1024 * 1024
print(out, hashlib.md5(open(out, "rb").read()).hexdigest(), "bot.py", hashlib.md5(data).hexdigest(), len(data))
