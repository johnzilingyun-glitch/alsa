import akshare as ak

def find_indicator_funcs():
    funcs = [f for f in dir(ak) if 'indicator' in f]
    print("Indicator functions:")
    for f in funcs:
        print(f" - {f}")

if __name__ == "__main__":
    find_indicator_funcs()
