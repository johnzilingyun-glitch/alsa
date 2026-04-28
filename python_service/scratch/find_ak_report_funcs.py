import akshare as ak
import pandas as pd

def find_report_funcs():
    funcs = [f for f in dir(ak) if 'report' in f and 'em' in f]
    print("Available EM report functions:")
    for f in funcs:
        print(f" - {f}")

if __name__ == "__main__":
    find_report_funcs()
