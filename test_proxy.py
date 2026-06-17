import requests
import os

for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]

os.environ['HTTP_PROXY'] = 'http://127.0.0.1:8118'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:8118'
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

print("Using proxies:", requests.utils.get_environ_proxies("https://push2.eastmoney.com"))

try:
    r = requests.get('https://push2.eastmoney.com/api/qt/stock/get?fltt=2&invt=2&fields=f43&secid=0.300274', timeout=5)
    print("Success:", r.status_code, r.text)
except Exception as e:
    print("Error:", e)
