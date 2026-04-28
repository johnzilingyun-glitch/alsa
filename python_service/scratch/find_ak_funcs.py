import akshare as ak
import pandas as pd

def find_financial_funcs():
    funcs = [f for f in dir(ak) if 'financial' in f and 'em' in f]
    print("Available EM financial functions:")
    for f in funcs:
        print(f" - {f}")

if __name__ == "__main__":
    find_financial_funcs()
